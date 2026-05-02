import requests
import re
from pathlib import Path

# Base URL for the ingest endpoint
BASE_URL = "http://localhost:8000/logs"

# Tournament map: section name -> tournament_id
TOURNAMENT_MAP = {
    "invite": 1,
    "qualifiers": 2,
    "R8": 2,
    "R7": 2,
    "R6": 2,
    "R5": 2,
    "R4": 2,
    "R3": 2,
    "R2": 2,
    "R1": 2,
    "main": 3
}

def parse_invite_file(filepath: str) -> list[tuple[int, int]]:
    """Parse invite.txt and return list of (log_id, tournament_id) tuples."""
    logs = []
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            
            if not line:
                continue
            
            # Check if this is a section header
            if line in TOURNAMENT_MAP:
                tournament_id = TOURNAMENT_MAP[line]
            
            # Extract log ID from full URL or just numeric ID
            if line.startswith("http://"):
                match = re.search(r'/ingest/(\d+)', line)
                if match:
                    log_id = int(match.group(1))
                    logs.append((log_id, tournament_id))
            elif line.isdigit():
                log_id = int(line)
                logs.append((log_id, tournament_id))
    
    return logs

def ingest_logs(logs: list[tuple[int, int]]) -> None:
    """Send POST requests to ingest all logs."""
    session = requests.Session()
    successful = 0
    failed = 0
    
    print(f"Starting ingestion of {len(logs)} logs...")
    print("-" * 60)
    
    for log_id, tournament_id in logs:
        try:
            url = f"{BASE_URL}/ingest/{log_id}"
            params = {"tournament_id": tournament_id}
            response = session.post(url, params=params, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Log {log_id} (Tournament {tournament_id}): {result['job_id']}")
                successful += 1
            else:
                print(f"✗ Log {log_id} (Tournament {tournament_id}): HTTP {response.status_code}")
                failed += 1
        except Exception as e:
            print(f"✗ Log {log_id} (Tournament {tournament_id}): {str(e)}")
            failed += 1
    
    print("-" * 60)
    print(f"Ingestion complete: {successful} successful, {failed} failed")


def check_jobs(logs: list[tuple[int, int]]):
    session = requests.Session()
    failures = 0
    for log_id, _tournament_id in logs:
        try:
            url = f"{BASE_URL}/status/{log_id}"
            response = session.get(url)
            if response.status_code == 200:
                result = response.json()
                status = result["status"]
            elif response.status_code == 404:
                status = "failed"
            else:
                status = "failed"
            if status == "failed":
                failures += 1
                print(f"{log_id}: {status}")
        except Exception as e:
            print(e)
    print("Total failures:", failures)


if __name__ == "__main__":
    file_path = Path(__file__).parent / "invite.txt"
    
    if not file_path.exists():
        print(f"Error: {file_path} not found")
        exit(1)
    
    logs = parse_invite_file(str(file_path))
    print(f"Parsed {len(logs)} log IDs from {file_path}")
    
    ingest_logs(logs)
    check_jobs(logs)
