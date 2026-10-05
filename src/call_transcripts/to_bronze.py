from src.utils import build_partitioned_bronze_command

main = build_partitioned_bronze_command("call_transcripts")

if __name__ == "__main__":
    main()
