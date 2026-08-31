#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STATE_DIR="${DASHBOARD_STATE_DIR:-${REPO_ROOT}/.cache/todoist-assistant/dashboard}"
PID_DIR="${DASHBOARD_PID_DIR:-${STATE_DIR}/pids}"
API_LOG_FILE="${STATE_DIR}/api.log"
OBSERVER_LOG_FILE="${STATE_DIR}/observer.log"
FRONTEND_LOG_FILE="${STATE_DIR}/frontend.log"

FRONTEND_PORT="${DASHBOARD_FRONTEND_PORT:-3000}"
API_PORT="${DASHBOARD_API_PORT:-8000}"

mkdir -p "${PID_DIR}" "${STATE_DIR}"

timestamp() {
    date +"%H:%M:%S"
}

log_note() {
    printf '[dashboard %s] %s\n' "$(timestamp)" "$*"
}

print_recent_log() {
    local label="${1}"
    local path="${2}"
    local lines="${3:-8}"
    [[ -f "${path}" ]] || return 0
    local excerpt
    excerpt="$(tail -n "${lines}" "${path}" 2>/dev/null | sed '/^[[:space:]]*$/d' || true)"
    [[ -n "${excerpt}" ]] || return 0
    log_note "${label} recent log lines:"
    while IFS= read -r line; do
        printf '    %s\n' "${line}"
    done <<< "${excerpt}"
}

is_running() {
    local pid_file="${1}"
    [[ -f "${pid_file}" ]] || return 1
    local pid
    pid="$(cat "${pid_file}" 2>/dev/null || true)"
    [[ -n "${pid}" ]] || return 1
    kill -0 "${pid}" 2>/dev/null
}

clear_stale_pid() {
    local pid_file="${1}"
    if [[ -f "${pid_file}" ]] && ! is_running "${pid_file}"; then
        rm -f "${pid_file}"
    fi
}

stop_pid_target() {
    local pid_file="${1}"
    local label="${2:-service}"
    [[ -f "${pid_file}" ]] || return 0
    local pid
    pid="$(cat "${pid_file}" 2>/dev/null || true)"
    [[ -n "${pid}" ]] || { rm -f "${pid_file}"; return 0; }
    log_note "Stopping ${label} (pid ${pid})..."

    local pgid
    pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
    if [[ -n "${pgid}" ]]; then
        kill -- "-${pgid}" 2>/dev/null || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            if ! ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' | grep -qx "${pgid}"; then
                break
            fi
            sleep 0.5
        done
        if ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' | grep -qx "${pgid}"; then
            kill -9 -- "-${pgid}" 2>/dev/null || true
        fi
    elif kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" 2>/dev/null || true
        sleep 0.5
        if kill -0 "${pid}" 2>/dev/null; then
            kill -9 "${pid}" 2>/dev/null || true
        fi
    fi
    rm -f "${pid_file}"
    log_note "${label} stopped."
}

wait_for_process() {
    local pid="${1}"
    local label="${2}"
    local tries=0
    while kill -0 "${pid}" 2>/dev/null; do
        tries=$((tries + 1))
        if [[ ${tries} -ge 10 ]]; then
            log_note "${label} process is alive (pid ${pid})."
            return 0
        fi
        sleep 0.2
    done
    echo "${label} exited before startup completed."
    return 1
}

wait_for_http() {
    local url="${1}"
    local label="${2}"
    local max_tries="${3:-120}"
    local sleep_s="${4:-0.5}"
    local tries=0
    log_note "Waiting for ${label} to be ready..."
    if command -v curl >/dev/null 2>&1; then
        until curl -fsS "${url}" >/dev/null 2>&1; do
            tries=$((tries + 1))
            if [[ ${tries} -ge ${max_tries} ]]; then
                echo "${label} readiness check timed out."
                return 1
            fi
            if (( tries % 10 == 0 )); then
                log_note "${label} still not ready after ${tries} checks..."
            fi
            sleep "${sleep_s}"
        done
    else
        sleep 5
    fi
    log_note "${label} is ready."
}

wait_for_api() {
    wait_for_http "http://127.0.0.1:${API_PORT}/api/health" "API" 60 0.5
}

wait_for_frontend() {
    wait_for_http "http://127.0.0.1:${FRONTEND_PORT}" "frontend" 120 0.5
}

port_listener_details() {
    local port="${1}"
    ss -ltnp "( sport = :${port} )" 2>/dev/null | tail -n +2 | sed '/^[[:space:]]*$/d'
}

port_listener_pids() {
    local port="${1}"
    ss -ltnp "( sport = :${port} )" 2>/dev/null \
        | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
        | sort -u
}

process_cmdline() {
    local pid="${1}"
    tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true
}

process_cwd() {
    local pid="${1}"
    readlink -f "/proc/${pid}/cwd" 2>/dev/null || true
}

is_repo_dashboard_process() {
    local pid="${1}"
    local service="${2}"
    local cwd cmd
    cwd="$(process_cwd "${pid}")"
    cmd="$(process_cmdline "${pid}")"
    case "${service}" in
        api)
            [[ "${cwd}" == "${REPO_ROOT}" && "${cmd}" == *"uvicorn todoist.web.api:app"* ]]
            ;;
        frontend)
            [[ "${cwd}" == "${REPO_ROOT}/frontend" && "${cmd}" == *"next"* ]]
            ;;
        *)
            return 1
            ;;
    esac
}

cleanup_stale_port_for_service() {
    local port="${1}"
    local label="${2}"
    local service="${3}"
    local cleaned=0
    local pid
    while IFS= read -r pid; do
        [[ -n "${pid}" ]] || continue
        if is_repo_dashboard_process "${pid}" "${service}"; then
            log_note "Cleaning up untracked ${label} process on port ${port} (pid ${pid})..."
            local tmp_pid_file="${PID_DIR}/.${service}-${pid}.stale.pid"
            printf '%s\n' "${pid}" > "${tmp_pid_file}"
            stop_pid_target "${tmp_pid_file}" "${label}"
            cleaned=1
        fi
    done < <(port_listener_pids "${port}")

    if [[ "${cleaned}" -eq 1 ]]; then
        sleep 0.5
    fi
}

ensure_port_free() {
    local port="${1}"
    local label="${2}"
    local details
    details="$(port_listener_details "${port}")"
    [[ -z "${details}" ]] && return 0
    echo "${label} cannot start because port ${port} is already in use."
    echo "${details}"
    echo "Stop the conflicting process or run make stop_dashboard if it is an earlier dashboard instance."
    return 1
}

cleanup_failed_launch() {
    log_note "Dashboard startup failed. Recent logs:"
    print_recent_log "API" "${API_LOG_FILE}" 20
    print_recent_log "Observer" "${OBSERVER_LOG_FILE}" 20
    print_recent_log "Frontend" "${FRONTEND_LOG_FILE}" 20
    stop_pid_target "${PID_DIR}/frontend.pid" "Frontend"
    stop_pid_target "${PID_DIR}/observer.pid" "Observer"
    stop_pid_target "${PID_DIR}/api.pid" "API"
}

backend_env_value() {
    local backend="${1}"
    case "${backend}" in
        raw) echo "disabled" ;;
        codex) echo "codex" ;;
        *) echo "disabled" ;;
    esac
}

start_dashboard() {
    local backend="${1}"
    local ai_backend
    ai_backend="$(backend_env_value "${backend}")"
    log_note "Launching dashboard stack (backend=${backend})..."
    for service in api observer frontend; do
        clear_stale_pid "${PID_DIR}/${service}.pid"
    done
    if is_running "${PID_DIR}/api.pid" || is_running "${PID_DIR}/observer.pid" || is_running "${PID_DIR}/frontend.pid"; then
        echo "Dashboard stack is already running. Use make stop_dashboard first."
        return 1
    fi
    cleanup_stale_port_for_service "${API_PORT}" "API" api
    cleanup_stale_port_for_service "${FRONTEND_PORT}" "Frontend" frontend
    ensure_port_free "${API_PORT}" "API"
    ensure_port_free "${FRONTEND_PORT}" "Frontend"

    trap cleanup_failed_launch ERR

    log_note "Starting API on 127.0.0.1:${API_PORT}..."
    nohup env TODOIST_AGENT_BACKEND="${ai_backend}" setsid uv run uvicorn todoist.web.api:app --host 127.0.0.1 --port "${API_PORT}" </dev/null > "${API_LOG_FILE}" 2>&1 &
    local api_pid="$!"
    echo "${api_pid}" > "${PID_DIR}/api.pid"
    wait_for_process "${api_pid}" "API"

    log_note "Starting observer..."
    nohup env HYDRA_FULL_ERROR=1 TODOIST_AGENT_BACKEND="${ai_backend}" setsid uv run python3 -m todoist.run_observer --config-dir configs --config-name automations </dev/null > "${OBSERVER_LOG_FILE}" 2>&1 &
    local observer_pid="$!"
    echo "${observer_pid}" > "${PID_DIR}/observer.pid"
    wait_for_process "${observer_pid}" "Observer"
    print_recent_log "Observer" "${OBSERVER_LOG_FILE}" 8

    wait_for_api
    print_recent_log "API" "${API_LOG_FILE}" 8

    log_note "Starting frontend on 127.0.0.1:${FRONTEND_PORT}..."
    nohup setsid npm --prefix frontend run dev -- --port "${FRONTEND_PORT}" </dev/null > "${FRONTEND_LOG_FILE}" 2>&1 &
    local frontend_pid="$!"
    echo "${frontend_pid}" > "${PID_DIR}/frontend.pid"
    wait_for_process "${frontend_pid}" "Frontend"

    wait_for_frontend
    print_recent_log "Frontend" "${FRONTEND_LOG_FILE}" 8

    trap - ERR

    log_note "Dashboard running (backend=${backend})."
    echo "  API:      http://127.0.0.1:${API_PORT}"
    if [[ "${backend}" == "raw" ]]; then
        echo "  Review:   disabled"
        echo "  Observer: enabled"
    else
        echo "  Review:   Codex on demand"
        echo "  Observer: enabled"
    fi
    echo "  Frontend: http://127.0.0.1:${FRONTEND_PORT}"
    echo "  Logs:     ${STATE_DIR}"
}

stop_dashboard() {
    local stopped=0
    log_note "Stopping dashboard stack..."

    for service in frontend observer api; do
        if [[ -f "${PID_DIR}/${service}.pid" ]]; then
            stopped=1
        fi
    done
    stop_pid_target "${PID_DIR}/frontend.pid" "Frontend"
    stop_pid_target "${PID_DIR}/observer.pid" "Observer"
    stop_pid_target "${PID_DIR}/api.pid" "API"

    if [[ ${stopped} -eq 0 ]]; then
        log_note "Dashboard stack is not running."
    else
        log_note "Dashboard stack stopped."
    fi
}

main() {
    local command="${1:-}"
    local backend="${2:-raw}"

    case "${command}" in
        start)
            if [[ "${backend}" != "raw" && "${backend}" != "codex" ]]; then
                echo "Usage: $0 start [raw|codex]"
                exit 1
            fi
            start_dashboard "${backend}"
            ;;
        stop)
            stop_dashboard
            ;;
        *)
            echo "Usage: $0 {start [raw|codex]|stop}"
            exit 1
            ;;
    esac
}

main "$@"
