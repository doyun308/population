
# main.py - 우리 동네 인구 타임머신 + 시군구 지도
# requirements.txt에는 plotly 한 줄만 입력하면 됩니다.
import json
import urllib.request

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="우리 동네 인구 탐구",
    page_icon="🏘️",
    layout="wide",
)

st.markdown("""
<style>
.stApp {background-color: #fff9f2;}
h1,h2,h3 {color: #634d40;}
div[data-testid="stMetric"] {
    background: #fffdf9;
    border: 1px solid #ead8c6;
    border-radius: 14px;
    padding: 14px;
}
</style>
""", unsafe_allow_html=True)


# 1. 데이터 파일 주소와 나이 목록
POP_URLS = [
    "https://raw.githubusercontent.com/first2022-cyber/contents/main/population_ts_yearly_gender.zip",
    "https://raw.githubusercontent.com/doyun308/population/main/population_ts_yearly_gender.zip",
]

MAP_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)

AGES = [f"{i}세" for i in range(100)] + ["100세 이상"]

M_COLS = ["남_" + a for a in AGES]
F_COLS = ["여_" + a for a in AGES]

NUM_COLS = M_COLS + F_COLS
KEY_COLS = ["연도", "시도", "시군구", "동"]


# 2. 인구 CSV ZIP 파일 불러오기
@st.cache_data(ttl=86400, show_spinner=False)
def load_population():
    errors = []

    for url in POP_URLS:
        for encoding in ("utf-8-sig", "cp949"):
            try:
                chunks = []

                reader = pd.read_csv(
                    url,
                    compression="zip",
                    encoding=encoding,
                    chunksize=4000,
                    low_memory=False,
                )

                for chunk in reader:
                    chunk.columns = (
                        chunk.columns.astype(str).str.strip()
                    )

                    missing = [
                        c for c in KEY_COLS + NUM_COLS
                        if c not in chunk.columns
                    ]

                    if missing:
                        raise ValueError(
                            "CSV 열 누락: "
                            + ", ".join(missing[:6])
                        )

                    chunk = chunk[
                        KEY_COLS + NUM_COLS
                    ].copy()

                    chunk["연도"] = pd.to_numeric(
                        chunk["연도"],
                        errors="coerce",
                    )

                    for col in ("시도", "시군구", "동"):
                        chunk[col] = (
                            chunk[col]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )

                    chunk = chunk.dropna(
                        subset=["연도"]
                    )

                    chunk = chunk.loc[
                        (chunk["시도"] != "")
                        & (chunk["시군구"] != "")
                        & (chunk["동"] != "")
                    ].copy()

                    if chunk.empty:
                        continue

                    chunk["연도"] = (
                        chunk["연도"].astype(int)
                    )

                    numbers = (
                        chunk[NUM_COLS]
                        .replace(",", "", regex=True)
                        .apply(
                            pd.to_numeric,
                            errors="coerce",
                        )
                        .fillna(0)
                    )

                    chunk = pd.concat(
                        [
                            chunk[KEY_COLS].reset_index(
                                drop=True
                            ),
                            numbers.reset_index(
                                drop=True
                            ),
                        ],
                        axis=1,
                    )

                    chunks.append(
                        chunk.groupby(
                            KEY_COLS,
                            as_index=False,
                        )[NUM_COLS].sum()
                    )

                if not chunks:
                    raise ValueError(
                        "유효한 인구 자료가 없습니다."
                    )

                df = pd.concat(
                    chunks,
                    ignore_index=True,
                )

                df = df.groupby(
                    KEY_COLS,
                    as_index=False,
                )[NUM_COLS].sum()

                df[NUM_COLS] = (
                    df[NUM_COLS]
                    .round()
                    .astype("int64")
                )

                years = sorted(
                    df["연도"].unique().tolist()
                )

                return df, years, url

            except Exception as exc:
                errors.append(
                    f"{url} / {encoding}: {exc}"
                )

    raise RuntimeError(
        "데이터를 읽지 못했습니다.\n"
        + "\n".join(errors)
    )


# 3. 지도 GeoJSON 파일 읽기
@st.cache_data(ttl=86400, show_spinner=False)
def load_geojson():
    with urllib.request.urlopen(
        MAP_URL,
        timeout=50,
    ) as response:
        geo = json.load(response)

    if (
        geo.get("type") != "FeatureCollection"
        or not geo.get("features")
    ):
        raise ValueError(
            "GeoJSON 형식 또는 features가 올바르지 않습니다."
        )

    return geo


# 4. 인구 통계 계산
def stats(male, female):
    counts = [
        m + f
        for m, f in zip(male, female)
    ]

    total = sum(counts)
    kid = sum(counts[:15])
    old = sum(counts[65:])

    return {
        "total": total,
        "male": sum(male),
        "female": sum(female),
        "kid": kid,
        "working": sum(counts[15:65]),
        "old": old,

        "kid_rate": (
            100 * kid / total if total else 0
        ),

        "old_rate": (
            100 * old / total if total else 0
        ),

        # 100세 이상은 100세로 간주한 추정치
        "mean": (
            sum(
                age * n
                for age, n in enumerate(counts)
            ) / total
            if total else None
        ),

        "aging_index": (
            100 * old / kid if kid else None
        ),

        "ages": counts,
    }


# 5. 시도 → 시군구 → 동 선택
def select_place(data, prefix, initial=None):
    cols = st.columns(3)

    a = sorted(
        data["시도"].unique().tolist()
    )

    with cols[0]:
        province = st.selectbox(
            "① 시도",
            a,
            index=(
                a.index(initial[0])
                if initial and initial[0] in a
                else 0
            ),
            key=prefix + "a",
        )

    sub = data.loc[
        data["시도"] == province
    ]

    b = sorted(
        sub["시군구"].unique().tolist()
    )

    with cols[1]:
        city = st.selectbox(
            "② 시군구",
            b,
            index=(
                b.index(initial[1])
                if initial and initial[1] in b
                else 0
            ),
            key=prefix + "b",
        )

    c = sorted(
        sub.loc[
            sub["시군구"] == city,
            "동",
        ].unique().tolist()
    )

    with cols[2]:
        town = st.selectbox(
            "③ 읍·면·동",
            c,
            index=(
                c.index(initial[2])
                if initial and initial[2] in c
                else 0
            ),
            key=prefix + "c",
        )

    return province, city, town


def place_rows(data, place):
    return data.loc[
        (data["시도"] == place[0])
        & (data["시군구"] == place[1])
        & (data["동"] == place[2])
    ]


def age_counts(rows, year):
    chosen = rows.loc[
        rows["연도"] == year
    ]

    if chosen.empty:
        return None

    male = (
        chosen[M_COLS]
        .sum()
        .astype(int)
        .tolist()
    )

    female = (
        chosen[F_COLS]
        .sum()
        .astype(int)
        .tolist()
    )

    return male, female


# 6. 인구 피라미드 그래프
def draw_pyramid(
    m,
    f,
    percentage=False,
    shared_bound=None,
    height=1100,
):
    total = max(sum(m) + sum(f), 1)

    factor = (
        100 / total if percentage else 1
    )

    # 남자는 음수: 왼쪽
    left = [-x * factor for x in m]

    # 여자는 양수: 오른쪽
    right = [x * factor for x in f]

    bound = (
        shared_bound
        if shared_bound is not None
        else max(
            max(m + f + [1]) * factor * 1.15,
            0.1,
        )
    )

    fig = go.Figure()

    fig.add_bar(
        x=left,
        y=AGES,
        orientation="h",
        name="남성",
        marker_color="#7aaccd",
        customdata=m,
        hovertemplate=(
            "남성 %{y}: %{customdata:,}명"
            "<extra></extra>"
        ),
    )

    fig.add_bar(
        x=right,
        y=AGES,
        orientation="h",
        name="여성",
        marker_color="#e99a94",
        customdata=f,
        hovertemplate=(
            "여성 %{y}: %{customdata:,}명"
            "<extra></extra>"
        ),
    )

    ticks = [
        -bound,
        -bound / 2,
        0,
        bound / 2,
        bound,
    ]

    labels = [
        (
            f"{abs(x):.1f}%"
            if percentage
            else f"{abs(x):,.0f}"
        )
        for x in ticks
    ]

    # 나이 축은 순서를 직접 고정합니다.
    fig.update_layout(
        barmode="relative",
        height=height,
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",

        margin=dict(
            l=55,
            r=20,
            t=40,
            b=45,
        ),

        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.04,
        ),

        xaxis=dict(
            title=(
                "전체 인구 대비 비율 (%)"
                if percentage else "인구수 (명)"
            ),
            range=[-bound, bound],
            tickmode="array",
            tickvals=ticks,
            ticktext=labels,
            zeroline=True,
            zerolinecolor="#ae9886",
        ),

        yaxis=dict(
            title="나이",
            type="category",

            # 아래 0세 → 위 100세 이상
            categoryorder="array",
            categoryarray=AGES,

            # 축 자체를 뒤집지 않습니다.
            range=[-0.5, 100.5],

            tickmode="array",
            tickvals=AGES[::10] + [AGES[-1]],
            ticktext=AGES[::10] + [AGES[-1]],
        ),
    )

    # 그래프 축 순서 검사
    assert (
        fig.layout.yaxis.categoryarray[0]
        == "0세"
    )

    assert (
        fig.layout.yaxis.categoryarray[-1]
        == "100세 이상"
    )

    assert (
        fig.layout.yaxis.range[0]
        < fig.layout.yaxis.range[1]
    )

    return fig


# 7. 총인구·평균연령·고령화율 카드
def show_cards(s):
    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👥 총인구",
        f"{s['total']:,}명",
    )

    c2.metric(
        "🎂 평균연령(추정)",
        (
            f"{s['mean']:.1f}세"
            if s["mean"] is not None
            else "자료 없음"
        ),
    )

    warning = (
        s["total"] > 0
        and s["old_rate"] > 20
    )

    c3.metric(
        "👵 고령화율"
        + (" ⚠️ 주의" if warning else ""),
        f"{s['old_rate']:.1f}%",
    )

    if warning:
        st.warning(
            "65세 이상 인구가 전체의 20%를 초과합니다."
        )


# 8. 아이와 어르신 인구 비교 설명
def summary(s):
    if not s["total"]:
        return (
            "이 동네는 인구가 0명으로 기록되어 "
            "분석할 수 없습니다."
        )

    if s["kid"] > s["old"]:
        word = (
            "아이(0~14세)가 어르신(65세 이상)"
            "보다 많은 지역입니다."
        )

    elif s["kid"] < s["old"]:
        word = (
            "어르신(65세 이상)이 아이(0~14세)"
            "보다 많은 지역입니다."
        )

    else:
        word = "아이와 어르신 수가 같은 지역입니다."

    return (
        f"{word} "
        f"아이 {s['kid_rate']:.1f}% · "
        f"어르신 {s['old_rate']:.1f}%"
    )


# 9. 연도별 인구 변화 표
def make_trend(rows):
    records = []

    for y in sorted(
        rows["연도"].unique().tolist()
    ):
        counts = age_counts(rows, y)

        if counts is None:
            continue

        s = stats(*counts)

        records.append({
            "연도": y,
            "총인구": s["total"],
            "평균연령(추정)": (
                round(s["mean"], 1)
                if s["mean"] is not None
                else None
            ),
            "아동 비율(%)": round(
                s["kid_rate"], 2
            ),
            "고령화율(%)": round(
                s["old_rate"], 2
            ),
        })

    return pd.DataFrame(records)


# 10. 연령별 상세 표
def make_age_table(m, f):
    total = max(sum(m) + sum(f), 1)

    return pd.DataFrame({
        "나이": AGES,
        "남성(명)": m,
        "여성(명)": f,

        "전체(명)": [
            x + y
            for x, y in zip(m, f)
        ],

        "비율(%)": [
            round(
                (x + y) / total * 100,
                2,
            )
            for x, y in zip(m, f)
        ],
    })


def download_csv(
    df,
    filename,
    label="📥 CSV 내려받기",
):
    st.download_button(
        label,
        data=(
            df.to_csv(index=False)
            .encode("utf-8-sig")
        ),
        file_name=filename,
        mime="text/csv",
    )


# 11. 지도에 필요한 시도 행정구역 코드
# 강원·전북의 이전/이후 코드를 함께 처리
PROVINCE_CODES = {
    "서울": ["11"],
    "부산": ["26"],
    "대구": ["27"],
    "인천": ["28"],
    "광주": ["29"],
    "대전": ["30"],
    "울산": ["31"],
    "세종": ["36"],
    "경기": ["41"],
    "강원": ["42", "51"],
    "충북": ["43"],
    "충남": ["44"],
    "전북": ["45", "52"],
    "전남": ["46"],
    "경북": ["47"],
    "경남": ["48"],
    "제주": ["50", "49"],

    "충청북": ["43"],
    "충청남": ["44"],
    "전라북": ["45", "52"],
    "전라남": ["46"],
    "경상북": ["47"],
    "경상남": ["48"],
}


def tidy(value):
    return (
        str(value)
        .replace(" ", "")
        .replace("·", "")
        .strip()
    )


def province_prefixes(province):
    clean = tidy(province)

    for name in sorted(
        PROVINCE_CODES,
        key=len,
        reverse=True,
    ):
        if clean.startswith(name):
            return PROVINCE_CODES[name]

    return []


# 12. 시군구별 통계와 GeoJSON 지도를 연결
def prepare_map(
    data,
    geo,
    province,
    year,
    indicator,
):
    # 동별 인구를 시군구 단위로 합산
    area = data.loc[
        (data["시도"] == province)
        & (data["연도"] == year)
    ]

    by_district = area.groupby(
        "시군구"
    )[NUM_COLS].sum()

    statistics_by_name = {}

    for district, row in by_district.iterrows():
        s = stats(
            row[M_COLS].astype(int).tolist(),
            row[F_COLS].astype(int).tolist(),
        )

        statistics_by_name[
            tidy(district)
        ] = s

    prefixes = province_prefixes(province)

    features = []
    matched = []
    names = []
    z_values = []

    # 지도 경계 정보를 한 지역씩 확인
    for item in geo["features"]:
        props = item.get("properties") or {}

        code = next(
            (
                str(props[x])
                for x in (
                    "SIG_CD",
                    "sig_cd",
                    "SIGUNGU_CD",
                    "code",
                )
                if props.get(x) is not None
            ),
            str(item.get("id", "")),
        )

        name = next(
            (
                str(props[x])
                for x in (
                    "SIG_KOR_NM",
                    "sig_kor_nm",
                    "SIGUNGU_NM",
                    "name",
                )
                if props.get(x)
            ),
            "",
        )

        if not code or not name:
            continue

        # 선택한 시도의 지도만 추출
        if (
            prefixes
            and code[:2] not in prefixes
        ):
            continue

        feat = {
            "type": "Feature",
            "id": code,
            "properties": props,
            "geometry": item.get("geometry"),
        }

        features.append(feat)

        target = tidy(name)

        if target in statistics_by_name:
            source = target

        else:
            # 예시:
            # CSV: 수원시 영통구
            # 지도: 영통구
            possibilities = [
                key
                for key in statistics_by_name
                if (
                    key.endswith(target)
                    or target.endswith(key)
                )
            ]

            source = (
                possibilities[0]
                if len(possibilities) == 1
                else None
            )

        if source is not None:
            s = statistics_by_name[source]

            value = {
                "고령화율(%)": s["old_rate"],
                "아동 비율(%)": s["kid_rate"],
                "총인구(명)": s["total"],
                "평균연령(세)": s["mean"],
            }[indicator]

            if value is not None:
                matched.append(code)
                names.append(name)
                z_values.append(value)

    if not features:
        raise ValueError(
            "선택한 시도의 시군구 경계를 "
            "GeoJSON에서 찾지 못했습니다."
        )

    # 지도상의 모든 시군구 경계를 먼저 그림
    collection = {
        "type": "FeatureCollection",
        "features": features,
    }

    all_codes = [
        feature["id"]
        for feature in features
    ]

    fig = go.Figure()

    # 데이터가 없는 곳은 연한 회색
    fig.add_trace(
        go.Choropleth(
            geojson=collection,
            featureidkey="id",
            locations=all_codes,
            z=[1] * len(all_codes),
            showscale=False,
            hoverinfo="skip",

            colorscale=[
                [0, "#eee6df"],
                [1, "#eee6df"],
            ],

            marker_line_color="#ffffff",
            marker_line_width=0.7,
        )
    )

    # 인구 통계가 연결된 지역을 색상으로 표시
    if matched:
        fig.add_trace(
            go.Choropleth(
                geojson=collection,
                featureidkey="id",
                locations=matched,
                z=z_values,
                text=names,
                colorscale="YlOrRd",

                colorbar_title=(
                    "명"
                    if indicator == "총인구(명)"
                    else (
                        "세"
                        if indicator == "평균연령(세)"
                        else "%"
                    )
                ),

                marker_line_color="#ffffff",
                marker_line_width=0.8,

                hovertemplate=(
                    "%{text}<br>"
                    + indicator
                    + ": %{z:,.1f}"
                    + "<extra></extra>"
                ),
            )
        )

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        projection_type="mercator",
    )

    fig.update_layout(
        height=600,

        margin=dict(
            l=0,
            r=0,
            t=25,
            b=0,
        ),

        paper_bgcolor="#fff9f2",
    )

    return fig, len(matched), len(features)


# 13. 실제 앱 화면
def main():

    st.title("🏘️ 우리 동네 인구 탐구실")

    st.write(
        "인구 피라미드 · 연도별 변화 · "
        "지역 비교 · 시군구 지도"
    )

    # 인구 파일 불러오기
    try:
        with st.spinner(
            "인구 데이터를 불러오는 중입니다. "
            "처음에는 시간이 걸릴 수 있습니다."
        ):
            data, years, source = (
                load_population()
            )

    except Exception as exc:
        st.error(
            "인구 데이터를 불러오지 못했습니다."
        )

        with st.expander(
            "자세한 오류 내용"
        ):
            st.code(str(exc))

        st.stop()

    st.caption(
        f"자료에 포함된 연도: "
        f"{years[0]}~{years[-1]}년"
    )

    # 지역 선택
    chosen_place = select_place(
        data,
        "main_",
    )

    selected = place_rows(
        data,
        chosen_place,
    )

    local_years = sorted(
        selected["연도"].unique().tolist()
    )

    place_name = " ".join(chosen_place)

    if not local_years:
        st.warning(
            "선택한 지역의 자료가 없습니다."
        )
        st.stop()

    # 다섯 가지 기능 탭
    tab1, tab2, tab3, tab4, tab5 = (
        st.tabs([
            "⏳ 인구 타임머신",
            "🗺️ 시군구 지도",
            "⚖️ 두 지역 비교",
            "📈 인구 변화",
            "📥 상세 분석",
        ])
    )

    # ================================
    # 탭 1: 인구 타임머신
    # ================================
    with tab1:
        year = st.select_slider(
            "연도",
            local_years,
            value=local_years[-1],
            key="year_main",
        )

        m, f = age_counts(
            selected,
            year,
        )

        s = stats(m, f)

        st.subheader(
            f"{year}년 {place_name}"
        )

        show_cards(s)

        percent = (
            st.radio(
                "표시 방식",
                ["인구수", "인구 비율(%)"],
                horizontal=True,
            )
            == "인구 비율(%)"
        )

        st.plotly_chart(
            draw_pyramid(m, f, percent),
            use_container_width=True,
        )

        st.info(
            "💡 이 동네는 아이가 많은 편인가요, "
            "어르신이 많은 편인가요? "
            + summary(s)
        )

        st.caption(
            "나이는 아래부터 0세 → 100세 이상 "
            "순서입니다. 남성은 왼쪽, "
            "여성은 오른쪽입니다."
        )

        download_csv(
            make_age_table(m, f),
            f"{year}_{chosen_place[2]}_인구.csv",
            "📥 현재 그래프 데이터 저장",
        )

    # ================================
    # 탭 2: 시군구 지도
    # ================================
    with tab2:
        st.subheader(
            f"🗺️ {chosen_place[0]} 시군구 인구 지도"
        )

        st.caption(
            "읍·면·동 자료를 시군구별로 합산했습니다. "
            "지도는 동 경계가 아닌 시군구 경계입니다."
        )

        map_years = sorted(
            data.loc[
                data["시도"] == chosen_place[0],
                "연도",
            ].unique().tolist()
        )

        c1, c2 = st.columns(2)

        with c1:
            map_year = st.selectbox(
                "지도 연도",
                map_years,
                index=len(map_years) - 1,
            )

        with c2:
            indicator = st.selectbox(
                "지도에 표시할 지표",
                [
                    "고령화율(%)",
                    "아동 비율(%)",
                    "총인구(명)",
                    "평균연령(세)",
                ],
            )

        try:
            with st.spinner(
                "지도 경계를 불러오는 중입니다..."
            ):
                geo = load_geojson()

                fig, matched, all_features = (
                    prepare_map(
                        data,
                        geo,
                        chosen_place[0],
                        map_year,
                        indicator,
                    )
                )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

            st.caption(
                f"색이 표시된 시군구: "
                f"{matched}/{all_features}개 · "
                f"회색은 데이터 연결이 안 된 곳입니다."
            )

            if matched == 0:
                st.warning(
                    "인구 데이터의 지역명과 지도 지역명이 "
                    "일치하지 않습니다. "
                    "원본 열 이름/행정구역 명칭을 "
                    "확인해 주세요."
                )

        except Exception as exc:
            st.error(
                "지도를 표시하지 못했습니다. "
                "원본 GeoJSON 주소 또는 "
                "행정구역 명칭을 확인해 주세요."
            )

            with st.expander(
                "지도 오류 상세"
            ):
                st.code(str(exc))

    # ================================
    # 탭 3: 두 지역 비교
    # ================================
    with tab3:
        st.subheader("⚖️ 두 동네 비교")

        options = sorted(
            data.loc[
                (
                    data["시도"]
                    == chosen_place[0]
                )
                & (
                    data["시군구"]
                    == chosen_place[1]
                ),
                "동",
            ].unique().tolist()
        )

        alternatives = [
            x for x in options
            if x != chosen_place[2]
        ]

        suggested = (
            (
                chosen_place[0],
                chosen_place[1],
                alternatives[0],
            )
            if alternatives
            else chosen_place
        )

        other_place = select_place(
            data,
            "compare_",
            suggested,
        )

        other = place_rows(
            data,
            other_place,
        )

        common = sorted(
            set(local_years)
            & set(
                other["연도"].unique().tolist()
            )
        )

        if not common:
            st.warning(
                "비교 가능한 공통 연도가 없습니다."
            )

        else:
            cyear = st.select_slider(
                "비교 연도",
                common,
                value=common[-1],
                key="year_compare",
            )

            percentage = (
                st.radio(
                    "비교 방식",
                    ["인구수", "인구 비율(%)"],
                    horizontal=True,
                    key="compare_mode",
                )
                == "인구 비율(%)"
            )

            m1, f1 = age_counts(
                selected, cyear
            )

            m2, f2 = age_counts(
                other, cyear
            )

            s1 = stats(m1, f1)
            s2 = stats(m2, f2)

            comp_table = pd.DataFrame({
                "지표": [
                    "총인구",
                    "평균연령(추정)",
                    "고령화율(%)",
                    "아동 비율(%)",
                ],

                place_name: [
                    s1["total"],
                    s1["mean"],
                    s1["old_rate"],
                    s1["kid_rate"],
                ],

                " ".join(other_place): [
                    s2["total"],
                    s2["mean"],
                    s2["old_rate"],
                    s2["kid_rate"],
                ],
            }).round(2)

            st.dataframe(
                comp_table,
                hide_index=True,
                use_container_width=True,
            )

            factor1 = (
                100 / max(s1["total"], 1)
                if percentage else 1
            )

            factor2 = (
                100 / max(s2["total"], 1)
                if percentage else 1
            )

            bound = max(
                max(m1 + f1 + [1]) * factor1,
                max(m2 + f2 + [1]) * factor2,
            ) * 1.15

            a, b = st.columns(2)

            with a:
                st.markdown(
                    "**A. " + place_name + "**"
                )

                st.plotly_chart(
                    draw_pyramid(
                        m1, f1,
                        percentage,
                        bound,
                        1050,
                    ),
                    use_container_width=True,
                )

            with b:
                st.markdown(
                    "**B. "
                    + " ".join(other_place)
                    + "**"
                )

                st.plotly_chart(
                    draw_pyramid(
                        m2, f2,
                        percentage,
                        bound,
                        1050,
                    ),
                    use_container_width=True,
                )

            st.caption(
                "같은 연도·같은 축 범위로 비교합니다. "
                "행정구역 개편이 있었다면 "
                "해석에 주의하세요."
            )

    # ================================
    # 탭 4: 인구 변화
    # ================================
