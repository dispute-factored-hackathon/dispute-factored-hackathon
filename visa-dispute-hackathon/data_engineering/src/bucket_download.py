import os
from pathlib import Path
import s3fs
from dotenv import load_dotenv

load_dotenv()

bucket = os.getenv("FACTORED_BUCKET_NAME")
bucket_data_folder = bucket + "/data"
copper_folder = Path("lakehouse/0-copper")

# Initialize S3FS client
fs = s3fs.S3FileSystem(
    key=os.getenv("FACTORED_ACCESS_KEY_ID"),
    secret=os.getenv("FACTORED_SECRET_ACCESS_KEY"),
    client_kwargs={"region_name": os.getenv("FACTORED_REGION")},
)

def download_file_if_not_exists(s3_path: str, local_path: Path):
    """Downloads a single file from S3, skipping it if it already exists locally."""
    if not fs.exists(s3_path):
            print(f"[Aviso - No encontrado en S3] {s3_path}")
            return

    if local_path.exists():
        print(f"[Skipping - Already exists] {local_path}")
        return

    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[Downloading file] {s3_path} -> {local_path}")
    fs.get(s3_path, str(local_path))

def download_folder_if_not_exists(s3_prefix: str, local_base_dir: Path):
    """Recursively downloads a directory from S3, skipping existing files."""
    print(f"\nScanning objects in: s3://{s3_prefix}...")
    files = fs.find(s3_prefix)

    for remote_file in files:
        # Calculate relative path relative to the remote prefix
        rel_path = os.path.relpath(remote_file, s3_prefix)
        local_dest = local_base_dir / rel_path

        # Prevent overwriting existing files
        if local_dest.exists():
            print(f"[Skipping - Already exists] {local_dest}")
            continue

        # Create missing partition subdirectories locally
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[Downloading] {remote_file} -> {local_dest}")
        fs.get(remote_file, str(local_dest))

if __name__ == "__main__":
    branches_s3 = f"{bucket_data_folder}/branches.csv"
    branches_local = copper_folder / "branches/branches.csv"
    download_file_if_not_exists(branches_s3, branches_local)

    call_center_interactions_s3 = f"{bucket_data_folder}/call_center_interactions"
    call_center_interactions_local = copper_folder / "call_center_interactions"
    download_folder_if_not_exists(call_center_interactions_s3, call_center_interactions_local)

    call_transcripts_s3 = f"{bucket_data_folder}/call_transcripts"
    call_transcripts_local = copper_folder / "call_transcripts"
    download_folder_if_not_exists(call_transcripts_s3, call_transcripts_local)

    complaints_s3 = f"{bucket_data_folder}/complaints"
    complaints_local = copper_folder / "complaints"
    download_folder_if_not_exists(complaints_s3, complaints_local)

    customers_s3 = f"{bucket_data_folder}/customers.csv"
    customers_local = copper_folder / "customers/customers.csv"
    download_file_if_not_exists(customers_s3, customers_local)
    
    products_s3 = f"{bucket_data_folder}/products.csv"
    products_local = copper_folder / "products/products.csv"
    download_file_if_not_exists(products_s3, products_local)

    service_agents_s3 = f"{bucket_data_folder}/service_agents.csv"
    service_agents_local = copper_folder / "service_agents/service_agents.csv"
    download_file_if_not_exists(service_agents_s3, service_agents_local)

    transactions_s3 = f"{bucket_data_folder}/transactions"
    transactions_local = copper_folder / "transactions"
    download_folder_if_not_exists(transactions_s3, transactions_local)

    print("\n✓ Synchronization process finished successfully.")