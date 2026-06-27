# -*- coding: utf-8 -*-
"""docx 텍스트 추출(의존성 없이 zipfile + xml). 인자: <docx 경로> [출력 txt 경로].

출력 경로 주면 파일로 저장(대용량 가이드용), 없으면 stdout.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

path = sys.argv[1]
out_path = sys.argv[2] if len(sys.argv) > 2 else None

# 텍스트 요소 <w:t> 만 매칭(<w:tbl>/<w:tc>/<w:tr> 등 동일 접두 태그 배제):
#   w:t 다음에 공백(속성) 또는 즉시 '>' 인 경우만.
T_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.S)


def _unescape(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'"))


with zipfile.ZipFile(path) as z:
    xml = z.read("word/document.xml").decode("utf-8", errors="replace")

# 표/문단 경계를 줄바꿈으로
xml = xml.replace("<w:tab/>", " ").replace("<w:br/>", "\n")
xml = re.sub(r"</w:tr>", "\n", xml)   # 표 행 경계
xml = re.sub(r"</w:p>", "\n", xml)    # 문단 경계

# 셀 경계는 ' | ' 로 (표 가독성)
xml = re.sub(r"</w:tc>", " | ", xml)

lines_out: list[str] = []
for chunk in xml.split("\n"):
    ts = T_RE.findall(chunk)
    line = _unescape("".join(ts)).strip()
    # 연속 ' |' 정리
    line = re.sub(r"(\s*\|\s*)+", " | ", line).strip(" |")
    if line:
        lines_out.append(line)

text = "\n".join(lines_out)
if out_path:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"saved {len(text)} chars → {out_path}")
else:
    print(text)
