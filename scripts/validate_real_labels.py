from __future__ import annotations

import json

from services.api.app.db import SessionLocal
from pipelines.ingest.labels import validate_real_label_export


def main() -> None:
    with SessionLocal() as session:
        result = validate_real_label_export(session=session, write_normalized=True)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
