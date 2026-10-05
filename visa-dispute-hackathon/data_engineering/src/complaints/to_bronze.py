from src.utils import build_partitioned_bronze_command

main = build_partitioned_bronze_command("complaints")

if __name__ == "__main__":
    main()
