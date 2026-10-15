
# 동네별 인구 피라미드 - Streamlit Community Cloud용 단일 파일
# 필요 라이브러리: streamlit, pandas, plotly

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# 1. 웹앱의 기본 설정과 디자인
st.set_page_config(
    page_title="동네별 인구 피라미드",
    page_icon="🏘️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp { background: #fff9f0; }
    .block-container { max-width: 1180px; padding-top: 2rem; }
    h1, h2, h3 { color: #644a3d; }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #f0dec7;
        border-radius: 15px;
        padding: 18px;
    }
    div[data-testid="stMetricValue"] { color: #60493f; }
    div[data-testid="stAlert"] { border-radius: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 첫 번째는 질문에 적힌 원본 URL,
# 두 번째는 연결된 GitHub 저장소의 원본 URL
DATA_URLS = [
    "https://raw.githubusercontent.com/first2022-cyber/contents/main/population_ts_yearly_gender.zip",
    "https://raw.githubusercontent.com/doyun308/population/main/population_ts_yearly_gender.zip",
]

# 연령은 반드시 0세 → 99세 → 100세 이상 순서로 만듭니다.
AGES = [f"{age}세" for age in range(100)] + ["100세 이상"]

MALE_COLUMNS = [f"남_{age}" for age in AGES]
FEMALE_COLUMNS = [f"여_{age}" for age in AGES]

REQUIRED_COLUMNS = (
    ["연도", "시도", "시군구", "동"]
    + MALE_COLUMNS
    + FEMALE_COLUMNS
)


# 2. ZIP 안에 있는 CSV를 pandas로 읽습니다.
# cache_data: 화면 조작 시 자료를 매번 다시 받지 않도록
# 하루 동안 저장합니다.
@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def load_latest_data():
    errors = []

    # 원본 주소가 동작하지 않으면 두 번째 주소를 시도합니다.
    for url in DATA_URLS:

        # CSV 인코딩이 다를 가능성도 처리합니다.
        for encoding in ["utf-8-sig", "cp949"]:
            try:
                newest_year = None
                newest_chunks = []

                # 파일을 여러 조각으로 읽으면서
                # 가장 최신 연도만 남깁니다.
                reader = pd.read_csv(
                    url,
                    compression="zip",
                    encoding=encoding,
                    chunksize=5000,
                    low_memory=False,
                )

                for chunk in reader:
                    chunk.columns = (
                        chunk.columns.astype(str).str.strip()
                    )

                    missing = [
                        col
                        for col in REQUIRED_COLUMNS
                        if col not in chunk.columns
                    ]

                    if missing:
                        raise ValueError(
                            "필요한 열이 없습니다: "
                            + ", ".join(missing[:8])
                        )

                    year_values = pd.to_numeric(
                        chunk["연도"],
                        errors="coerce",
                    )

                    chunk_max = year_values.max()

                    if pd.isna(chunk_max):
                        continue

                    # 더 최신 연도를 발견하면
                    # 이전 연도 데이터를 버립니다.
                    if (
                        newest_year is None
                        or chunk_max > newest_year
                    ):
                        newest_year = int(chunk_max)

                        newest_chunks = [
                            chunk.loc[
                                year_values == chunk_max
                            ].copy()
                        ]

                    elif int(chunk_max) == newest_year:
                        newest_chunks.append(
                            chunk.loc[
                                year_values == newest_year
                            ].copy()
                        )

                if not newest_chunks:
                    raise ValueError(
                        "연도 데이터를 찾을 수 없습니다."
                    )

                latest = pd.concat(
                    newest_chunks,
                    ignore_index=True,
                )

                # 지역 이름의 불필요한 공백을 없앱니다.
                for col in ["시도", "시군구", "동"]:
                    latest[col] = (
                        latest[col]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                    )

                # 지역 이름이 없는 합계 행 등을 제외합니다.
                latest = latest[
                    (latest["시도"] != "")
                    & (latest["시군구"] != "")
                    & (latest["동"] != "")
                ].copy()

                if latest.empty:
                    raise ValueError(
                        "선택할 수 있는 읍·면·동 행이 없습니다."
                    )

                return latest, newest_year, url

            except Exception as exc:
                errors.append(
                    f"{url} ({encoding}): {exc}"
                )

    raise RuntimeError(
        "데이터를 불러오지 못했습니다.\n"
        + "\n".join(errors)
    )


# 3. 선택한 동네의 남녀 인구를 연령별로 계산합니다.
def sum_by_age(selected_rows, column_names):

    # '1,234'와 같은 값도 숫자로 변환합니다.
    values = (
        selected_rows[column_names]
        .astype(str)
        .replace(",", "", regex=True)
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .sum(axis=0)
    )

    # 같은 지역의 행이 여러 개라면 합산합니다.
    return [
        int(value)
        for value in values.tolist()
    ]


# 4. 인구 피라미드 그래프를 만듭니다.
def create_pyramid(
    male_counts,
    female_counts,
    total_population,
    percent_mode,
):

    # 인구 비율 표시를 선택한 경우
    if percent_mode:
        denominator = (
            total_population
            if total_population > 0
            else 1
        )

        male_values = [
            -100 * count / denominator
            for count in male_counts
        ]

        female_values = [
            100 * count / denominator
            for count in female_counts
        ]

    # 일반 인구수를 선택한 경우
    else:
        male_values = [
            -count for count in male_counts
        ]

        female_values = female_counts

    fig = go.Figure()

    # 남자는 음수 → 왼쪽
    fig.add_trace(
        go.Bar(
            x=male_values,
            y=AGES,
            orientation="h",
            name="남성",
            marker_color="#7ca7ca",
            customdata=male_counts,
            hovertemplate=(
                "남성 · %{y}"
                "<br>%{customdata:,}명"
                "<extra></extra>"
            ),
        )
    )

    # 여자는 양수 → 오른쪽
    fig.add_trace(
        go.Bar(
            x=female_values,
            y=AGES,
            orientation="h",
            name="여성",
            marker_color="#ec9c8d",
            customdata=female_counts,
            hovertemplate=(
                "여성 · %{y}"
                "<br>%{customdata:,}명"
                "<extra></extra>"
            ),
        )
    )

    # 양쪽 그래프의 범위를 같게 합니다.
    largest = max(
        [abs(v) for v in male_values + female_values]
        + [0.1]
    )

    bound = largest * 1.12

    tick_values = [
        -bound,
        -bound / 2,
        0,
        bound / 2,
        bound,
    ]

    if percent_mode:
        tick_labels = [
            f"{abs(v):.1f}%"
            for v in tick_values
        ]
        x_title = "전체 인구 대비 비율 (%)"

    else:
        tick_labels = [
            f"{abs(v):,.0f}"
            for v in tick_values
        ]
        x_title = "인구수 (명)"

    fig.update_layout(
        height=1320,
        barmode="relative",

        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",

        font=dict(
            family=(
                "Malgun Gothic, "
                "Apple SD Gothic Neo, sans-serif"
            ),
            color="#624d43",
        ),

        margin=dict(
            l=65,
            r=35,
            t=50,
            b=55,
        ),

        legend=dict(
            orientation="h",
            x=0.5,
            y=1.03,
            xanchor="center",
            yanchor="bottom",
        ),

        xaxis=dict(
            title=x_title,
            range=[-bound, bound],
            tickmode="array",
            tickvals=tick_values,
            ticktext=tick_labels,
            gridcolor="#f1e7da",
            zeroline=True,
            zerolinecolor="#ae9586",
            zerolinewidth=2,
        ),

        yaxis=dict(
            title="나이",
            type="category",

            # 핵심 설정!
            # 나이를 오름차순으로 고정합니다.
            # 첫 범주는 아래, 마지막 범주는 위입니다.
            categoryorder="array",
            categoryarray=AGES,

            # 0세가 아래, 100세 이상이 위입니다.
            range=[
                -0.5,
                len(AGES) - 0.5,
            ],

            # 10세 간격으로 눈금을 보여줍니다.
            tickmode="array",
            tickvals=AGES[::10],
            ticktext=AGES[::10],
            showgrid=False,
        ),
    )

    # 그래프 생성 후 나이 순서를 확인합니다.
    assert fig.layout.yaxis.categoryarray[0] == "0세"

    assert (
        fig.layout.yaxis.categoryarray[-1]
        == "100세 이상"
    )

    assert (
        fig.layout.yaxis.range[0]
        < fig.layout.yaxis.range[1]
    )

    return fig


# 5. 실제 웹앱 화면을 구성합니다.
st.title("🏘️ 동네별 인구 피라미드")

st.write(
    "전국 읍·면·동 중 원하는 동네를 선택하고 "
    "남녀·연령별 인구를 살펴보세요."
)

try:
    with st.spinner(
        "최신 인구 데이터를 불러오는 중입니다..."
    ):
        data, latest_year, data_url = (
            load_latest_data()
        )

except Exception as exc:
    st.error(
        "인구 데이터 연결에 실패했습니다. "
        "GitHub 파일 주소와 인터넷 연결을 확인해 주세요."
    )

    with st.expander("자세한 오류 내용"):
        st.code(str(exc))

    st.stop()

st.caption(
    f"📅 자료에 포함된 최신 연도: "
    f"**{latest_year}년** · 데이터: GitHub ZIP 파일"
)


# 6. 시도 → 시군구 → 동을 순서대로 선택합니다.
col1, col2, col3 = st.columns(3)

with col1:
    province = st.selectbox(
        "① 시도 선택",
        sorted(data["시도"].unique()),
    )

province_rows = data.loc[
    data["시도"] == province
]

with col2:
    district = st.selectbox(
        "② 시군구 선택",
        sorted(province_rows["시군구"].unique()),
    )

district_rows = province_rows.loc[
    province_rows["시군구"] == district
]

with col3:
    neighborhood = st.selectbox(
        "③ 동(읍·면) 선택",
        sorted(district_rows["동"].unique()),
    )

selected_rows = district_rows.loc[
    district_rows["동"] == neighborhood
]


# 7. 선택 지역의 인구 통계를 계산합니다.
male = sum_by_age(
    selected_rows,
    MALE_COLUMNS,
)

female = sum_by_age(
    selected_rows,
    FEMALE_COLUMNS,
)

all_ages = [
    m + f
    for m, f in zip(male, female)
]

male_total = sum(male)
female_total = sum(female)

all_total = male_total + female_total

# 0~14세
children = sum(all_ages[:15])

# 15~64세
working_age = sum(all_ages[15:65])

# 65세 이상
seniors = sum(all_ages[65:])

senior_rate = (
    seniors / all_total * 100
    if all_total
    else 0
)


# 8. 화면 상단에 주요 통계를 보여줍니다.
st.subheader(
    f"📍 {province} {district} {neighborhood}"
)

metric1, metric2, metric3, metric4 = (
    st.columns(4)
)

metric1.metric(
    "전체 인구",
    f"{all_total:,}명",
)

metric2.metric(
    "남성 인구",
    f"{male_total:,}명",
)

metric3.metric(
    "여성 인구",
    f"{female_total:,}명",
)

metric4.metric(
    "65세 이상 비율",
    f"{senior_rate:.1f}%",
)

if all_total == 0:
    st.warning(
        "이 지역의 인구가 0명으로 집계되었습니다. "
        "원본 데이터를 확인해 주세요."
    )


# 추가 기능 ①: 인구수 / 인구 비율 전환
show_mode = st.radio(
    "그래프 표시 방식",
    [
        "인구수(명)",
        "인구 비율(%)",
    ],
    horizontal=True,
)

percent_mode = (
    show_mode == "인구 비율(%)"
)


# 9. 상세 인구표를 만듭니다.
detail_table = pd.DataFrame(
    {
        "나이": AGES,
        "남성(명)": male,
        "여성(명)": female,
        "전체(명)": all_ages,
    }
)

detail_table["전체 대비 비율(%)"] = (
    (
        detail_table["전체(명)"]
        / all_total
        * 100
    ).round(2)
    if all_total
    else 0.0
)


# 10. 화면을 세 개의 탭으로 나눕니다.
pyramid_tab, groups_tab, table_tab = (
    st.tabs(
        [
            "📊 인구 피라미드",
            "🧒 연령대별 분석",
            "📥 상세 표·다운로드",
        ]
    )
)


# 첫 번째 탭: 인구 피라미드
with pyramid_tab:

    st.plotly_chart(
        create_pyramid(
            male,
            female,
            all_total,
            percent_mode,
        ),
        use_container_width=True,
        config={
            "displaylogo": False
        },
    )

    st.caption(
        "파란색은 남성(왼쪽), "
        "분홍색은 여성(오른쪽)입니다. "
        "아래는 0세, 위는 100세 이상입니다."
    )


# 추가 기능 ②: 연령대별 통계
with groups_tab:

    group_names = [
        "0~14세",
        "15~64세",
        "65세 이상",
    ]

    group_counts = [
        children,
        working_age,
        seniors,
    ]

    group_table = pd.DataFrame(
        {
            "연령대": group_names,
            "인구수(명)": group_counts,
            "전체 대비 비율(%)": [
                round(
                    v / all_total * 100,
                    1,
                )
                if all_total
                else 0
                for v in group_counts
            ],
        }
    )

    st.dataframe(
        group_table,
        hide_index=True,
        use_container_width=True,
    )

    # 추가 기능 ③: 연령대별 도넛 그래프
    if all_total > 0:

        donut = go.Figure(
            go.Pie(
                labels=group_names,
                values=group_counts,
                hole=0.55,
                marker=dict(
                    colors=[
                        "#e9bd74",
                        "#8bb4aa",
                        "#d49487",
                    ]
                ),
                textinfo="label+percent",
                hovertemplate=(
                    "%{label}: %{value:,}명 "
                    "(%{percent})"
                    "<extra></extra>"
                ),
            )
        )

        donut.update_layout(
            height=410,

            margin=dict(
                l=15,
                r=15,
                t=20,
                b=20,
            ),

            paper_bgcolor="#fff9f0",

            font=dict(
                family="Malgun Gothic, sans-serif"
            ),

            showlegend=False,
        )

        st.plotly_chart(
            donut,
            use_container_width=True,
            config={
                "displaylogo": False
            },
        )

        # 추가 기능 ④: 가장 인구가 많은 나이
        largest_age_index = max(
            range(len(all_ages)),
            key=lambda i: all_ages[i],
        )

        st.info(
            f"가장 인구가 많은 나이는 "
            f"**{AGES[largest_age_index]}**이며, "
            f"총 "
            f"**{all_ages[largest_age_index]:,}명**입니다."
        )

    st.caption(
        "연령대 구분: "
        "유소년 0~14세 / "
        "생산연령 15~64세 / "
        "고령 65세 이상"
    )


# 세 번째 탭: 상세 데이터와 CSV 다운로드
with table_tab:

    st.dataframe(
        detail_table,
        hide_index=True,
        use_container_width=True,
        height=520,
    )

    # 엑셀에서 한글이 깨지는 현상을 방지합니다.
    csv_bytes = (
        detail_table
        .to_csv(index=False)
        .encode("utf-8-sig")
    )

    st.download_button(
        label="📥 이 동네의 연령별 인구 CSV 다운로드",
        data=csv_bytes,
        file_name=(
            f"인구피라미드_"
            f"{latest_year}_"
            f"{province}_"
            f"{district}_"
            f"{neighborhood}.csv"
        ),
        mime="text/csv",
    )

    st.caption(
        "엑셀에서 한글이 깨지지 않도록 "
        "UTF-8(BOM) 형식으로 저장합니다."
    )


# 11. 자료 출처를 표시합니다.
st.divider()

st.caption(
    "출처: 제공된 GitHub 인구 데이터 · "
    "자료에 포함된 최신 연도 기준으로 표시됩니다."
)
