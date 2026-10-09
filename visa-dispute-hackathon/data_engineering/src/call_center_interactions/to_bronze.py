from src.utils import build_partitioned_bronze_command

main = build_partitioned_bronze_command("call_center_interactions")

if __name__ == "__main__":
    main()
