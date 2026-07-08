import shutil
from datetime import datetime
from pathlib import Path

import db

BACKUP_DIR = Path(__file__).parent / "data" / "backups"
KEEP_BACKUPS = 14


def create_backup() -> Path | None:
    if not db.DB_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = BACKUP_DIR / f"archivist_{stamp}.db"
    shutil.copy2(db.DB_PATH, target)

    backups = sorted(BACKUP_DIR.glob("archivist_*.db"))
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink()

    return target
