# fetcher가 시세 가져옴, validatiors가 시세 검사 >> 검사 통과 시 저장! (저장형식 : Parquet)
# Parquet 저장 (data/market/)
# - raw/<source>/: 수집한 원본 그대로, std/: data/schema.py 표준으로 변환한 것 (연구·운용은 std만 읽는다)
# - 파일마다 수집일·소스·스키마 버전을 메타데이터로 남긴다
# - 임시 파일에 쓴 뒤 교체해서 반쯤 쓴 파일이 남지 않게 한다 (폴더가 없으면 만든다)


#저장필요한 도구들 .. 
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import pyarrow as pa
import pyarrow.parquet as pq

from .schema import SCHEMA_VERSION


def save_prices(result, root: Path, filename: str) -> Path:      #원본과 표준본 각각 어디에 저장할지 ..
    collected = datetime.now(timezone.utc).isoformat().encode()
    raw_path = root / "raw" / result.provider.replace(":", "_") / filename
    std_path = root / "std" / filename
    for path, data, version in (              
        (raw_path, result.raw, b"raw"),
        (std_path, result.data, SCHEMA_VERSION.encode()),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(data)
        metadata = dict(table.schema.metadata or {})
        metadata.update(source=result.provider.encode(), collected_at=collected, schema_version=version)
        with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temp_path = Path(temporary.name)
        try:
            pq.write_table(table.replace_schema_metadata(metadata), temp_path)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
    return std_path
