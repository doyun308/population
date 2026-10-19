"""동네별 인구 피라미드: 시간여행·지역 비교·고령화 추세 분석.

Streamlit Community Cloud에서 main.py 하나로 실행됩니다.
필요 추가 패키지: plotly (requirements.txt)
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ── 데이터 위치와 공통 설정 ─────────────────────────────────────────
# GitHub의 /blob/ 주소가 아니라 CSV ZIP 파일의 raw 주소를 씁니다.
DATA_URLS = [
    "https://raw.githubusercontent.com/first2022-cyber/contents/main/population_ts_yearly_gender.zip",
    "https://raw.githubusercontent.com/doyun308/population/main/population_ts_yearly_gender.zip",
]

# 나이를 크기순으로 자동 정렬하지 않고 직접 순서를 지정합니다.
AGES = [f"{i}세" for i in range(100)] + ["100세 이상"]
AGE_VALUES = list(range(101))  # 100세 이상은 평균 계산 시 100세로 간주
MALE_COLS = [f"남_{age}" for age in AGES]
FEMALE_COLS = [f"여_{age}" for age in AGES]
POP_COLS = MALE_COLS + FEMALE_COLS
KEY_COLS = ["연도", "시도", "시군구", "동"]
REQUIRED = KEY_COLS + POP_COLS


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def load_data():
    """ZIP의 모든 연도를 읽고, 동일 연도·동네 행을 합쳐 저장합니다."""
    errors = []
    for url in DATA_URLS:
        for encoding in ("utf-8-sig", "cp949"):
            try:
                pieces = []
                reader = pd.read_csv(
                    url,
                    compression="zip",
                    encoding=encoding,
                    chunksize=4000,
                    low_memory=False,
                )
                for piece in reader:
                    piece.columns = piece.columns.astype(str).str.strip()
                    missing = [c for c in REQUIRED if c not in piece.columns]
                    if missing:
                        raise ValueError("CSV 열 누락: " + ", ".join(missing[:8]))

                    # 필요한 열만 사용하여 메모리를 절약합니다.
                    piece = piece[REQUIRED].copy()
                    piece["연도"] = pd.to_numeric(piece["연도"], errors="coerce")
                    for field in ("시도", "시군구", "동"):
                        piece[field] = piece[field].fillna("").astype(str).str.strip()
                    piece = piece.dropna(subset=["연도"])
                    piece = piece.loc[
                        (piece["시도"] != "")
                        & (piece["시군구"] != "")
                        & (piece["동"] != "")
                    ].copy()
                    if piece.empty:
                        continue

                    piece["연도"] = piece["연도"].astype(int)
                    # 1,234 같은 문자열과 결측값도 처리합니다.
                    numeric = piece[POP_COLS].replace(",", "", regex=True)
                    numeric = numeric.apply(pd.to_numeric, errors="coerce").fillna(0)
                    # 202개 열을 하나씩 대입하면 속도가 느려질 수 있어 한번에 결합합니다.
                    piece = pd.concat(
                        [piece[KEY_COLS].reset_index(drop=True), numeric.reset_index(drop=True)],
                        axis=1,
                    )

                    # 동명이 같은 읍·면·동이 여러 행이면 합계 처리합니다.
                    pieces.append(
                        piece.groupby(KEY_COLS, as_index=False, sort=False)[POP_COLS].sum()
                    )

                if not pieces:
                    raise ValueError("읽을 수 있는 연도/지역 정보가 없습니다.")

                full = pd.concat(pieces, ignore_index=True)
                full = full.groupby(KEY_COLS, as_index=False, sort=False)[POP_COLS].sum()
                full[POP_COLS] = full[POP_COLS].round().astype("int64")
                years = sorted(full["연도"].unique().tolist())
                return full, years, url

            except Exception as exc:
                errors.append(f"{url} / {encoding}: {exc}")

    raise RuntimeError("데이터 파일을 열지 못했습니다.\n" + "\n".join(errors))


def rows_for_place(data, place):
    """(시도, 시군구, 동)로 해당 지역의 모든 연도를 선택합니다."""
    sido, sigungu, dong = place
