from todoist.runtime_env import load_local_dotenv, resolve_llm_backend


def main() -> None:
    load_local_dotenv()
    backend = resolve_llm_backend()
    print("" if backend == "disabled" else backend)


if __name__ == "__main__":
    main()
