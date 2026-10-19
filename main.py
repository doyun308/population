
# main.py - 동네별 인구 피라미드와 전국 시군구 지도
# requirements.txt에는 plotly만 입력하면 됩니다.

import json
from urllib.request import urlopen

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="우리 동네 인구 분석",
    page_icon="🏘️",
    layout="wide"
)

st.markdown("""
<style>
.stApp {background:#fff9f1}
h1,h2,h3 {color:#654c40}
[data-testid="stMetric"] {
    background:white;
    padding:14px;
    border:1px solid #eadacc;
    border-radius:14px;
}
</style>
""", unsafe_allow_html=True)


# 1. 데이터 파일 주소
POP_URLS = [
    "https://raw.githubusercontent.com/first2022-cyber/contents/main/population_ts_yearly_gender.zip",
    "https://raw.githubusercontent.com/doyun308/population/main/population_ts_yearly_gender.zip",
]

MAP_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)

AGES = [f"{i}세" for i in range(100)] + ["100세 이상"]

MALE = ["남_" + age for age in AGES]
FEMALE = ["여_" + age for age in AGES]

NUMERIC = MALE + FEMALE
KEYS = ["연도", "시도", "시군구", "동"]


# 2. 전국 인구 데이터 불러오기
@st.cache_data(ttl=86400, show_spinner=False)
def load_population():
    messages = []

    for url in POP_URLS:
        for enc in ("utf-8-sig", "cp949"):
            try:
                parts = []

                reader = pd.read_csv(
                    url,
                    compression="zip",
                    encoding=enc,
                    chunksize=4000,
                    low_memory=False
                )

                for chunk in reader:
                    chunk.columns = (
                        chunk.columns.astype(str).str.strip()
                    )

                    missing = [
                        c for c in KEYS + NUMERIC
                        if c not in chunk.columns
                    ]

                    if missing:
                        raise ValueError(
                            "필수 열 없음: " + ", ".join(missing[:8])
                        )

                    part = chunk[KEYS].copy()

                    part["연도"] = pd.to_numeric(
                        part["연도"], errors="coerce"
                    )

                    for col in KEYS[1:]:
                        part[col] = (
                            part[col]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )

                    valid = (
                        part["연도"].notna()
                        & part["시도"].ne("")
                        & part["시군구"].ne("")
                        & part["동"].ne("")
                    )

                    if not valid.any():
                        continue

                    part = (
                        part.loc[valid]
                        .copy()
                        .reset_index(drop=True)
                    )

                    part["연도"] = part["연도"].astype(int)

                    nums = chunk.loc[
                        valid, NUMERIC
                    ].replace(",", "", regex=True)

                    nums = (
                        nums.apply(
                            pd.to_numeric, errors="coerce"
                        )
                        .fillna(0)
                        .reset_index(drop=True)
                        .astype("int32")
                    )

                    part = pd.concat(
                        [part, nums], axis=1
                    )

                    parts.append(
                        part.groupby(
                            KEYS, as_index=False
                        )[NUMERIC].sum()
                    )

                if not parts:
                    raise ValueError("읽을 수 있는 인구 행이 없습니다.")

                data = pd.concat(
                    parts, ignore_index=True
                )

                data = data.groupby(
                    KEYS, as_index=False
                )[NUMERIC].sum()

                data[NUMERIC] = data[NUMERIC].astype("int32")

                years = sorted(
                    data["연도"].unique().tolist()
                )

                return data, years

            except Exception as ex:
                messages.append(
                    f"{url} / {enc}: {ex}"
                )

    raise RuntimeError(
        "데이터 다운로드 실패\n"
        + "\n".join(messages)
    )


# 3. GeoJSON 지도 읽기
@st.cache_data(ttl=86400, show_spinner=False)
def load_map():
    with urlopen(MAP_URL, timeout=40) as response:
        geo = json.load(response)

    if (
        geo.get("type") != "FeatureCollection"
        or not geo.get("features")
    ):
        raise ValueError("GeoJSON 형식이 아닙니다.")

    return geo


# 4. 인구 통계 계산
def metrics(m, f):
    counts = [a + b for a, b in zip(m, f)]

    total = sum(counts)
    kids = sum(counts[:15])
    old = sum(counts[65:])

    return {
        "total": total,
        "male": sum(m),
        "female": sum(f),
        "kids": kids,
        "old": old,
        "working": sum(counts[15:65]),

        "kids_pct": (
            100 * kids / total if total else 0
        ),

        "old_pct": (
            100 * old / total if total else 0
        ),

        # 100세 이상은 100세로 계산한 추정치
        "mean": (
            sum(
                i * n for i, n in enumerate(counts)
            ) / total
            if total else None
        ),

        "aging": (
            100 * old / kids if kids else None
        ),

        "counts": counts
    }


# 5. 선택 연도의 남녀 인구
def age_numbers(rows, year):
    row = rows.loc[rows["연도"] == year]

    if row.empty:
        return None

    return (
        row[MALE].sum().astype(int).tolist(),
        row[FEMALE].sum().astype(int).tolist()
    )


# 6. 시도 → 시군구 → 동 선택
def place_select(data, key, suggested=None):
    a, b, c = st.columns(3)

    with a:
        opts = sorted(data["시도"].unique())

        province = st.selectbox(
            "시도",
            opts,
            index=(
                opts.index(suggested[0])
                if suggested and suggested[0] in opts
                else 0
            ),
            key=key + "a"
        )

    local = data.loc[data["시도"] == province]

    with b:
        opts = sorted(local["시군구"].unique())

        district = st.selectbox(
            "시군구",
            opts,
            index=(
                opts.index(suggested[1])
                if suggested and suggested[1] in opts
                else 0
            ),
            key=key + "b"
        )

    with c:
        opts = sorted(
            local.loc[
                local["시군구"] == district, "동"
            ].unique()
        )

        dong = st.selectbox(
            "읍·면·동",
            opts,
            index=(
                opts.index(suggested[2])
                if suggested and suggested[2] in opts
                else 0
            ),
            key=key + "c"
        )

    return province, district, dong


def rows_for(data, place):
    a, b, c = place

    return data.loc[
        (data["시도"] == a)
        & (data["시군구"] == b)
        & (data["동"] == c)
    ]


# 7. 인구 피라미드
def pyramid(
    m, f,
    percent=False,
    limit=None,
    height=1150
):
    total = max(sum(m) + sum(f), 1)
    scale = 100 / total if percent else 1

    # 남자는 음수, 여자는 양수
    left = [-x * scale for x in m]
    right = [x * scale for x in f]

    bound = (
        limit
        if limit is not None
        else max(
            max(m + f + [1]) * scale * 1.15,
            0.1
        )
    )

    fig = go.Figure()

    fig.add_bar(
        x=left,
        y=AGES,
        name="남성",
        orientation="h",
        customdata=m,
        marker_color="#79aacb",
        hovertemplate=(
            "남성 %{y}: %{customdata:,}명"
            "<extra></extra>"
        )
    )

    fig.add_bar(
        x=right,
        y=AGES,
        name="여성",
        orientation="h",
        customdata=f,
        marker_color="#e99b92",
        hovertemplate=(
            "여성 %{y}: %{customdata:,}명"
            "<extra></extra>"
        )
    )

    ticks = [
        -bound, -bound/2, 0, bound/2, bound
    ]

    ticktext = [
        f"{abs(v):.1f}%"
        if percent else f"{abs(v):,.0f}"
        for v in ticks
    ]

    fig.update_layout(
        barmode="relative",
        height=height,
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",

        margin=dict(
            l=75, r=25, t=35, b=55
        ),

        xaxis=dict(
            range=[-bound, bound],
            title=(
                "전체 인구 대비 비율(%)"
                if percent else "인구수(명)"
            ),
            tickmode="array",
            tickvals=ticks,
            ticktext=ticktext
        ),

        yaxis=dict(
            type="category",

            # 맨 아래 0세, 맨 위 100세 이상
            categoryorder="array",
            categoryarray=AGES,
            range=[-0.5, 100.5],

            tickmode="array",
            tickvals=AGES[::10] + [AGES[-1]],
            ticktext=AGES[::10] + [AGES[-1]]
        ),

        legend=dict(
            orientation="h",
            y=1.04,
            x=0.5,
            xanchor="center"
        )
    )

    # 축 순서 검사
    assert fig.layout.yaxis.categoryarray[0] == "0세"
    assert fig.layout.yaxis.categoryarray[-1] == "100세 이상"
    assert fig.layout.yaxis.range[0] < fig.layout.yaxis.range[1]

    return fig


# 8. 지표 카드
def cards(s):
    a, b, c = st.columns(3)

    a.metric(
        "👥 총인구",
        f"{s['total']:,}명"
    )

    b.metric(
        "🎂 평균연령(추정)",
        (
            f"{s['mean']:.1f}세"
            if s["mean"] is not None
            else "자료 없음"
        )
    )

    warning = (
        s["total"] > 0
        and s["old_pct"] > 20
    )

    c.metric(
        "👵 고령화율"
        + (" ⚠️ 주의" if warning else ""),
        f"{s['old_pct']:.1f}%"
    )

    if warning:
        st.warning(
            "65세 이상 인구 비율이 20%를 초과합니다."
        )


# 9. 동네 특징 자동 설명
def explanation(s):
    if not s["total"]:
        return "인구수가 0명으로 기록되어 분석할 수 없습니다."

    if s["kids"] > s["old"]:
        msg = "아이가 더 많습니다."

    elif s["kids"] < s["old"]:
        msg = "어르신이 더 많습니다."

    else:
        msg = "아이와 어르신 수가 같습니다."

    return (
        f"{msg} "
        f"(0~14세 {s['kids_pct']:.1f}%, "
        f"65세 이상 {s['old_pct']:.1f}%)"
    )


# 10. 연령별 상세 데이터
def age_table(m, f):
    total = max(sum(m) + sum(f), 1)

    return pd.DataFrame({
        "나이": AGES,
        "남성(명)": m,
        "여성(명)": f,
        "전체(명)": [
            x + y for x, y in zip(m, f)
        ],
        "전체 비율(%)": [
            round(100 * (x+y) / total, 2)
            for x, y in zip(m, f)
        ]
    })


# 11. 연도별 변화 데이터
def timeline(rows):
    result = []

    for y in sorted(rows["연도"].unique()):
        values = age_numbers(rows, y)

        if values is None:
            continue

        s = metrics(*values)

        result.append({
            "연도": y,
            "총인구": s["total"],
            "아동 비율(%)": s["kids_pct"],
            "고령화율(%)": s["old_pct"],
            "평균연령(추정)": s["mean"]
        })

    return pd.DataFrame(result)


# 12. CSV 다운로드
def download(df, name):
    st.download_button(
        "📥 데이터 CSV 저장",
        data=df.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name=name,
        mime="text/csv"
    )


# 13. 행정구역 코드
REGIONS = {
    "서울": "11",
    "부산": "26",
    "대구": "27",
    "인천": "28",
    "광주": "29",
    "대전": "30",
    "울산": "31",
    "세종": "36",
    "경기": "41",
    "강원": "42",
    "충청북": "43",
    "충북": "43",
    "충청남": "44",
    "충남": "44",
    "전라북": "45",
    "전북": "45",
    "전라남": "46",
    "전남": "46",
    "경상북": "47",
    "경북": "47",
    "경상남": "48",
    "경남": "48",
    "제주": "50"
}


def compact(s):
    return str(s).replace(" ", "").replace("·", "")


def geo_info(feature):
    p = feature.get("properties") or {}

    code = str(
        next(
            (
                p[k]
                for k in (
                    "SIG_CD",
                    "sig_cd",
                    "SIGUNGU_CD",
                    "sigungu_cd",
                    "code",
                    "CODE"
                )
                if p.get(k) is not None
            ),
            feature.get("id", "")
        )
    )

    name = str(
        next(
            (
                p[k]
                for k in (
                    "SIG_KOR_NM",
                    "sig_kor_nm",
                    "SIGUNGU_NM",
                    "sigungu_nm",
                    "name",
                    "NAME"
                )
                if p.get(k)
            ),
            ""
        )
    )

    return code, name


# 14. 시군구 지도 생성
def district_map(
    data, geo, province, year, measure
):
    rows = data.loc[
        (data["시도"] == province)
        & (data["연도"] == year)
    ]

    districts = rows.groupby(
        "시군구"
    )[NUMERIC].sum()

    sums = {
        compact(name): metrics(
            row[MALE].astype(int).tolist(),
            row[FEMALE].astype(int).tolist()
        )
        for name, row in districts.iterrows()
    }

    prefix = next(
        (
            v for k, v in REGIONS.items()
            if compact(province).startswith(k)
        ),
        None
    )

    if prefix is None:
        raise ValueError(
            "시도 행정코드 확인 필요: " + province
        )

    # 특별자치도 이전/이후 행정구역 코드
    prefixes = (
        {"42", "51"}
        if prefix == "42"
        else (
            {"45", "52"}
            if prefix == "45"
            else {prefix}
        )
    )

    if prefix == "50":
        prefixes.add("49")

    features = []
    codes = []
    values = []
    labels = []
    records = []

    for obj in geo["features"]:
        code, name = geo_info(obj)

        if code[:2] not in prefixes or not name:
            continue

        feature = dict(obj)
        feature["id"] = code
        features.append(feature)

        normalized = compact(name)

        matches = [
            key for key in sums
            if (
                key == normalized
                or key.endswith(normalized)
            )
        ]

        if len(matches) != 1:
            continue

        s = sums[matches[0]]

        value = {
            "고령화율(%)": s["old_pct"],
            "아동 비율(%)": s["kids_pct"],
            "총인구(명)": s["total"],
            "평균연령(세)": s["mean"]
        }[measure]

        if value is None:
            continue

        codes.append(code)
        labels.append(name)
        values.append(value)

        records.append({
            "시군구": matches[0],
            "총인구(명)": s["total"],
            "고령화율(%)": round(
                s["old_pct"], 1
            ),
            "아동 비율(%)": round(
                s["kids_pct"], 1
            )
        })

    if not features:
        raise ValueError(
            "이 시도의 시군구 경계를 찾을 수 없습니다."
        )

    fc = {
        "type": "FeatureCollection",
        "features": features
    }

    fig = go.Figure()

    # 인구와 연결되지 않은 지역은 회색 표시
    fig.add_trace(
        go.Choropleth(
            geojson=fc,
            featureidkey="id",
            locations=[
                f["id"] for f in features
            ],
            z=[0] * len(features),
            colorscale=[
                [0, "#e7e4df"],
                [1, "#e7e4df"]
            ],
            showscale=False,
            hoverinfo="skip",
            marker_line_color="white"
        )
    )

    # 인구 통계가 있는 지역은 색상 표시
    if codes:
        fig.add_trace(
            go.Choropleth(
                geojson=fc,
                featureidkey="id",
                locations=codes,
                z=values,
                text=labels,
                colorscale="YlOrRd",
                colorbar_title=measure,
                marker_line_color="white",
                hovertemplate=(
                    "%{text}<br>%{z:,.1f}"
                    "<extra></extra>"
                )
            )
        )

    fig.update_geos(
        fitbounds="locations",
        visible=False
    )

    fig.update_layout(
        height=620,
        margin=dict(
            l=0, r=0, t=10, b=0
        ),
        paper_bgcolor="#fff9f1"
    )

    return fig, pd.DataFrame(records), len(features)


# ========================================
# 15. 실제 앱 화면
# ========================================

st.title("🏘️ 우리 동네 인구 탐구실")

st.write(
    "연도별 인구 피라미드 · 전국 시군구 지도 · "
    "두 동네 비교 · 고령화 변화"
)

try:
    with st.spinner(
        "전국 인구 데이터를 불러오는 중입니다..."
    ):
        data, years = load_population()

except Exception as e:
    st.error(
        "인구 CSV를 읽지 못했습니다. "
        "아래 오류 내용을 확인하세요."
    )
    st.code(str(e))
    st.stop()

st.caption(
    f"자료에 들어 있는 연도: "
    f"{years[0]}~{years[-1]}년"
)

place = place_select(data, "area_")
rows = rows_for(data, place)

local_years = sorted(
    rows["연도"].unique().tolist()
)

place_name = " ".join(place)

if not local_years:
    st.warning("선택 지역에 자료가 없습니다.")
    st.stop()


# 다섯 가지 기능 탭
t1, t2, t3, t4, t5 = st.tabs([
    "⏳ 타임머신",
    "🗺️ 시군구 지도",
    "⚖️ 지역 비교",
    "📈 변화 추세",
    "📥 상세 분석"
])


# ========================================
# TAB 1. 인구 타임머신
# ========================================
with t1:
    year = st.select_slider(
        "연도",
        local_years,
        value=local_years[-1],
        key="time_year"
    )

    m, f = age_numbers(rows, year)
    s = metrics(m, f)

    st.subheader(
        f"{place_name} · {year}년"
    )

    cards(s)

    percent = (
        st.radio(
            "표시 방식",
            ["인구수", "비율(%)"],
            horizontal=True,
            key="mode"
        )
        == "비율(%)"
    )

    st.plotly_chart(
        pyramid(m, f, percent),
        use_container_width=True,
        key="pyramid_main"
    )

    st.info(
        "💡 이 동네는 아이가 많은 편인가요, "
        "어르신이 많은 편인가요? "
        + explanation(s)
    )

    download(
        age_table(m, f),
        f"{year}_{place[2]}_인구.csv"
    )


# ========================================
# TAB 2. 전국 시군구 지도
# ========================================
with t2:
    st.subheader("🗺️ 시군구별 인구 지도")

    st.caption(
        "읍·면·동 인구를 시군구로 합산한 지도입니다. "
        "읍·면·동 경계는 표시되지 않습니다."
    )

    a, b = st.columns(2)

    pyears = sorted(
        data.loc[
            data["시도"] == place[0],
            "연도"
        ].unique()
    )

    with a:
        map_year = st.selectbox(
            "지도 연도",
            pyears,
            index=len(pyears)-1
        )

    with b:
        indicator = st.selectbox(
            "색상 기준",
            [
                "고령화율(%)",
                "아동 비율(%)",
                "총인구(명)",
                "평균연령(세)"
            ]
        )

    try:
        geo = load_map()

        fig, table, all_count = district_map(
            data,
            geo,
            place[0],
            map_year,
            indicator
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            key="map_chart"
        )

        st.caption(
            f"지도와 연결된 시군구: "
            f"{len(table)}/{all_count}곳. "
            "회색은 연결되지 않은 곳입니다."
        )

        if table.empty:
            st.warning(
                "지도 지역 이름과 인구 데이터의 "
                "지역 이름이 일치하지 않습니다."
            )

        else:
            st.dataframe(
                table.sort_values(
                    "고령화율(%)",
                    ascending=False
                ),
                hide_index=True,
                use_container_width=True
            )

            download(
                table,
                f"{place[0]}_{map_year}_시군구.csv"
            )

    except Exception as e:
        st.error(
            "지도를 불러오지 못했습니다. "
            "GeoJSON 파일 또는 열 이름을 확인하세요."
        )
        st.code(str(e))


# ========================================
# TAB 3. 두 동네 비교
# ========================================
with t3:
    st.subheader("⚖️ 두 동네 비교")

    same_area = sorted(
        data.loc[
            (data["시도"] == place[0])
            & (data["시군구"] == place[1]),
            "동"
        ].unique()
    )

    others = [
        x for x in same_area
        if x != place[2]
    ]

    guess = (
        place[0],
        place[1],
        others[0] if others else place[2]
    )

    other = place_select(
        data,
        "compare_",
        guess
    )

    other_rows = rows_for(data, other)

    common_years = sorted(
        set(local_years)
        & set(other_rows["연도"].unique())
    )

    if not common_years:
        st.warning(
            "공통으로 비교할 수 있는 연도가 없습니다."
        )

    else:
        cy = st.select_slider(
            "비교 연도",
            common_years,
            value=common_years[-1]
        )

        m1, f1 = age_numbers(rows, cy)
        m2, f2 = age_numbers(other_rows, cy)

        s1 = metrics(m1, f1)
        s2 = metrics(m2, f2)

        comparison = pd.DataFrame({
            "지표": [
                "총인구(명)",
                "평균연령(추정)",
                "고령화율(%)",
                "아동 비율(%)"
            ],
            "지역 A": [
                s1["total"],
                s1["mean"],
                s1["old_pct"],
                s1["kids_pct"]
            ],
            "지역 B": [
                s2["total"],
                s2["mean"],
                s2["old_pct"],
                s2["kids_pct"]
            ]
        }).round(2)

        st.dataframe(
            comparison,
            hide_index=True,
            use_container_width=True
        )

        compare_percent = st.checkbox(
            "인구 비율(%)로 비교",
            key="comp_percent"
        )

        a_scale = (
            100 / max(s1["total"], 1)
            if compare_percent else 1
        )

        b_scale = (
            100 / max(s2["total"], 1)
            if compare_percent else 1
        )

        # 두 그래프의 눈금 범위를 같게 설정
        bound = 1.15 * max(
            max(m1 + f1 + [1]) * a_scale,
            max(m2 + f2 + [1]) * b_scale
        )

        a, b = st.columns(2)

        with a:
            st.write("**A · " + place_name + "**")

            st.plotly_chart(
                pyramid(
                    m1, f1,
                    compare_percent,
                    bound,
                    1000
                ),
                use_container_width=True,
                key="compare_a"
            )

        with b:
            st.write(
                "**B · " + " ".join(other) + "**"
            )

            st.plotly_chart(
                pyramid(
                    m2, f2,
                    compare_percent,
                    bound,
                    1000
                ),
                use_container_width=True,
                key="compare_b"
            )

        st.caption(
            "두 그래프는 같은 연도와 "
            "같은 가로축 범위를 사용합니다."
        )


# ========================================
# TAB 4. 인구 변화 추세
# ========================================
with t4:
    st.subheader(
        f"📈 {place_name} 인구 변화"
    )

    trend = timeline(rows)

    st.dataframe(
        trend.round(2),
        hide_index=True,
        use_container_width=True
    )

    fig = go.Figure()

    fig.add_scatter(
        x=trend["연도"],
        y=trend["아동 비율(%)"],
        name="아동 비율",
        mode="lines+markers"
    )

    fig.add_scatter(
        x=trend["연도"],
        y=trend["고령화율(%)"],
        name="고령화율",
        mode="lines+markers"
    )

    fig.add_hline(
        y=20,
        line_dash="dot",
        annotation_text="고령화율 20% 참고선"
    )

    fig.update_layout(
        height=400,
        xaxis_title="연도",
        yaxis_title="%",
        paper_bgcolor="#fffdf8"
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="trend_fig"
    )

    st.line_chart(
        trend.set_index("연도")["총인구"]
    )

    if len(trend) > 1:
        first = trend.iloc[0]
        last = trend.iloc[-1]

        population_change = int(
            last["총인구"] - first["총인구"]
        )

        aging_change = (
            last["고령화율(%)"]
            - first["고령화율(%)"]
        )

        st.info(
            f"{int(first['연도'])}년 → "
            f"{int(last['연도'])}년: "
            f"총인구 {population_change:+,}명, "
            f"고령화율 {aging_change:+.2f}%p"
        )

    download(
        trend.round(2),
        f"{place[2]}_연도별변화.csv"
    )


# ========================================
# TAB 5. 상세 데이터 분석
# ========================================
with t5:
    st.subheader("📥 상세 연령 분석")

    year = st.selectbox(
        "상세 데이터 연도",
        local_years,
        index=len(local_years)-1
    )

    m, f = age_numbers(rows, year)
    s = metrics(m, f)

    a, b, c = st.columns(3)

    a.metric(
        "0~14세",
        f"{s['kids']:,}명"
    )

    b.metric(
        "15~64세",
        f"{s['working']:,}명"
    )

    c.metric(
        "65세 이상",
        f"{s['old']:,}명"
    )

    st.metric(
        "노령화지수(아동 100명당 어르신)",
        (
            f"{s['aging']:.1f}"
            if s["aging"] is not None
            else "계산 불가"
        )
    )

    if s["total"]:
        pie = go.Figure(
            go.Pie(
                labels=[
                    "0~14세",
                    "15~64세",
                    "65세 이상"
                ],
                values=[
                    s["kids"],
                    s["working"],
                    s["old"]
                ],
                hole=0.55
            )
        )

        pie.update_layout(
            height=330,
            paper_bgcolor="#fffdf8"
        )

        st.plotly_chart(
            pie,
            use_container_width=True,
            key="age_pie"
        )

        # 가장 인구가 많은 나이
        i = max(
            range(101),
            key=lambda i: s["counts"][i]
        )

        st.info(
            f"가장 인구가 많은 나이: "
            f"{AGES[i]} "
            f"({s['counts'][i]:,}명)"
        )

    table = age_table(m, f)

    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True
    )

    download(
        table,
        f"{year}_{place[2]}_상세.csv"
    )


# 16. 자료 출처
st.divider()

st.caption(
    "자료: 제공된 GitHub 인구 CSV ZIP 및 시군구 GeoJSON · "
    "평균연령은 100세 이상을 100세로 계산한 추정치입니다."
)
