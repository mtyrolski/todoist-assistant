#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STATE_DIR="${DASHBOARD_STATE_DIR:-${REPO_ROOT}/.cache/todoist-assistant/dashboard}"
PID_DIR="${DASHBOARD_PID_DIR:-${STATE_DIR}/pids}"
TRITON_MODE_FILE="${STATE_DIR}/triton.mode"
TRITON_LOG_FILE="${STATE_DIR}/triton.log"
TRITON_LOG_PID_FILE="${PID_DIR}/triton-log.pid"
API_LOG_FILE="${STATE_DIR}/api.log"
OBSERVER_LOG_FILE="${STATE_DIR}/observer.log"
FRONTEND_LOG_FILE="${STATE_DIR}/frontend.log"

FRONTEND_PORT="${DASHBOARD_FRONTEND_PORT:-3000}"
API_PORT="${DASHBOARD_API_PORT:-8000}"
TRITON_HTTP_PORT="${TODOIST_TRITON_HTTP_PORT:-8003}"

TRITON_MODEL_ID="${TRITON_MODEL_ID:-Qwen/Qwen2.5-0.5B-Instruct}"
TRITON_MODEL_NAME="${TRITON_MODEL_NAME:-todoist_llm}"
TRITON_URL="${TRITON_URL:-http://127.0.0.1:${TRITON_HTTP_PORT}}"

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

compose_files_for_mode() {
    local mode="${1}"
    COMPOSE_FILES=(
        -f "${REPO_ROOT}/compose.yaml"
    )
    if [[ "${mode}" == "gpu" ]]; then
        COMPOSE_FILES+=(-f "${REPO_ROOT}/compose.triton.gpu.yaml")
    fi
}

docker_compose() {
    local mode="${1}"
    shift
    compose_files_for_mode "${mode}"
    (
        cd "${REPO_ROOT}"
        COMPOSE_PROFILES=dashboard docker compose "${COMPOSE_FILES[@]}" "$@"
    )
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

require_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "Docker daemon is unavailable. Ensure your user can access the Docker socket before running dashboard targets."
        return 1
    fi
}

require_gpu_runtime() {
    local runtimes
    runtimes="$(docker info --format '{{json .Runtimes}}' 2>/dev/null || true)"
    if ! grep -q '"nvidia"' <<<"${runtimes}"; then
        echo "Docker NVIDIA runtime is unavailable. Use make run_dashboard_cpu or install the NVIDIA Container Toolkit before using make run_dashboard_gpu."
        return 1
    fi
}

start_triton() {
    local mode="${1}"
    log_note "Starting Triton (${mode}) for model ${TRITON_MODEL_NAME} <- ${TRITON_MODEL_ID}..."
    require_docker
    if [[ "${mode}" == "gpu" ]]; then
        require_gpu_runtime
    fi

    if [[ -f "${TRITON_LOG_PID_FILE}" ]]; then
        local triton_log_pid
        triton_log_pid="$(cat "${TRITON_LOG_PID_FILE}" 2>/dev/null || true)"
        if [[ -n "${triton_log_pid}" ]] && kill -0 "${triton_log_pid}" 2>/dev/null; then
            kill "${triton_log_pid}" 2>/dev/null || true
        fi
        rm -f "${TRITON_LOG_PID_FILE}"
    fi

    local triton_device="cpu"
    local triton_dtype="float32"
    if [[ "${mode}" == "gpu" ]]; then
        triton_device="cuda"
        triton_dtype="float16"
    fi

    (
        export TODOIST_AGENT_TRITON_MODEL_ID="${TRITON_MODEL_ID}"
        export TODOIST_AGENT_TRITON_MODEL_NAME="${TRITON_MODEL_NAME}"
        export TODOIST_TRITON_DEVICE="${TODOIST_TRITON_DEVICE:-${triton_device}}"
        export TODOIST_TRITON_MODEL_DTYPE="${TODOIST_TRITON_MODEL_DTYPE:-${triton_dtype}}"
        export TODOIST_TRITON_TORCH_INSTALL_FLAVOR="${mode}"
        export TODOIST_TRITON_PYTHON_SHM_PREFIX="todoist_$(date +%s)"
        docker_compose "${mode}" up -d --build triton
    )
    nohup bash -lc "cd '${REPO_ROOT}' && COMPOSE_PROFILES=dashboard docker compose ${COMPOSE_FILES[*]} logs -f --no-color triton" > "${TRITON_LOG_FILE}" 2>&1 &
    echo "$!" > "${TRITON_LOG_PID_FILE}"
    echo "${mode}" > "${TRITON_MODE_FILE}"
    wait_for_http "http://127.0.0.1:${TRITON_HTTP_PORT}/v2/health/ready" "Triton" 900 1
    print_recent_log "Triton" "${TRITON_LOG_FILE}" 10
}

stop_triton() {
    local mode="${1:-cpu}"
    if [[ -f "${TRITON_MODE_FILE}" ]]; then
        mode="$(cat "${TRITON_MODE_FILE}" 2>/dev/null || echo "${mode}")"
    fi
    compose_files_for_mode "${mode}"
    log_note "Stopping Triton (${mode})..."

    if [[ -f "${TRITON_LOG_PID_FILE}" ]]; then
        local triton_log_pid
        triton_log_pid="$(cat "${TRITON_LOG_PID_FILE}" 2>/dev/null || true)"
        if [[ -n "${triton_log_pid}" ]] && kill -0 "${triton_log_pid}" 2>/dev/null; then
            log_note "Stopping Triton log tail (${triton_log_pid})..."
            kill "${triton_log_pid}" 2>/dev/null || true
        fi
        rm -f "${TRITON_LOG_PID_FILE}"
    fi

    docker_compose "${mode}" stop triton >/dev/null 2>&1 || true
    docker_compose "${mode}" rm -f triton >/dev/null 2>&1 || true
    rm -f "${TRITON_MODE_FILE}"
    log_note "Triton stopped."
}

cleanup_failed_launch() {
    local mode="${1}"
    log_note "Dashboard startup failed. Recent logs:"
    print_recent_log "Triton" "${TRITON_LOG_FILE}" 20
    print_recent_log "API" "${API_LOG_FILE}" 20
    print_recent_log "Observer" "${OBSERVER_LOG_FILE}" 20
    print_recent_log "Frontend" "${FRONTEND_LOG_FILE}" 20
    stop_triton "${mode}"
    stop_pid_target "${PID_DIR}/frontend.pid" "Frontend"
    stop_pid_target "${PID_DIR}/observer.pid" "Observer"
    stop_pid_target "${PID_DIR}/api.pid" "API"
}

start_dashboard() {
    local mode="${1}"
    log_note "Launching dashboard stack in ${mode} mode..."
    for service in api observer frontend triton; do
        clear_stale_pid "${PID_DIR}/${service}.pid"
    done
    if is_running "${PID_DIR}/api.pid" || is_running "${PID_DIR}/observer.pid" || is_running "${PID_DIR}/frontend.pid"; then
        echo "Dashboard stack is already running. Use make stop_dashboard first."
        return 1
    fi
    ensure_port_free "${API_PORT}" "API"
    ensure_port_free "${FRONTEND_PORT}" "Frontend"
    ensure_port_free "${TRITON_HTTP_PORT}" "Triton"

    trap 'cleanup_failed_launch "'"${mode}"'"' ERR

    start_triton "${mode}"

    log_note "Starting API on 127.0.0.1:${API_PORT}..."
    nohup env TODOIST_AGENT_TRITON_MODEL_ID="${TRITON_MODEL_ID}" TODOIST_AGENT_TRITON_MODEL_NAME="${TRITON_MODEL_NAME}" TODOIST_AGENT_TRITON_URL="${TRITON_URL}" setsid uv run uvicorn todoist.web.api:app --host 127.0.0.1 --port "${API_PORT}" </dev/null > "${API_LOG_FILE}" 2>&1 &
    local api_pid="$!"
    echo "${api_pid}" > "${PID_DIR}/api.pid"
    wait_for_process "${api_pid}" "API"

    log_note "Starting observer..."
    nohup env HYDRA_FULL_ERROR=1 TODOIST_AGENT_TRITON_MODEL_ID="${TRITON_MODEL_ID}" TODOIST_AGENT_TRITON_MODEL_NAME="${TRITON_MODEL_NAME}" TODOIST_AGENT_TRITON_URL="${TRITON_URL}" setsid uv run python3 -m todoist.run_observer --config-dir configs --config-name automations </dev/null > "${OBSERVER_LOG_FILE}" 2>&1 &
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

    log_note "Dashboard running (${mode} Triton)."
    echo "  Triton:   http://127.0.0.1:${TRITON_HTTP_PORT}"
    echo "  API:      http://127.0.0.1:${API_PORT}"
    echo "  Observer: enabled with dashboard startup"
    echo "  Frontend: http://127.0.0.1:${FRONTEND_PORT}"
    echo "  Logs:     ${STATE_DIR}"
}

stop_dashboard() {
    local stopped=0
    log_note "Stopping dashboard stack..."

    if [[ -f "${TRITON_LOG_PID_FILE}" ]] || [[ -f "${TRITON_MODE_FILE}" ]]; then
        stopped=1
    fi
    if docker ps -a --format '{{.Names}}' | grep -qx 'todoist-assistant-triton-1'; then
        stopped=1
    fi
    stop_triton

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

triton_shell() {
    local mode="cpu"
    local exec_args=()
    require_docker
    if [[ -f "${TRITON_MODE_FILE}" ]]; then
        mode="$(cat "${TRITON_MODE_FILE}" 2>/dev/null || echo "cpu")"
    fi
    compose_files_for_mode "${mode}"
    if ! docker_compose "${mode}" ps --status running --services 2>/dev/null | grep -qx 'triton'; then
        echo "Triton is not running. Start it with make run_dashboard_cpu or make run_dashboard_gpu first."
        return 1
    fi
    if [[ ! -t 0 || ! -t 1 ]]; then
        exec_args+=(-T)
    fi
    docker_compose "${mode}" exec "${exec_args[@]}" triton bash
}

main() {
    local command="${1:-}"
    local mode="${2:-cpu}"

    case "${command}" in
        start)
            if [[ "${mode}" != "cpu" && "${mode}" != "gpu" ]]; then
                echo "Usage: $0 start [cpu|gpu]"
                exit 1
            fi
            start_dashboard "${mode}"
            ;;
        stop)
            stop_dashboard
            ;;
        triton-shell)
            triton_shell
            ;;
        *)
            echo "Usage: $0 {start [cpu|gpu]|stop|triton-shell}"
            exit 1
            ;;
    esac
}

main "$@"
