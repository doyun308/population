"""동네별 인구 피라미드 - Streamlit Community Cloud용 단일 파일.

실행: streamlit run main.py
추가 설치: plotly (requirements.txt)
"""

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

# 첫 번째는 요청한 원본 주소, 두 번째는 함께 제공된 GitHub 주소입니다.
# GitHub 웹페이지의 /blob/ 주소가 아닌 원본 파일 URL을 사용해야 합니다.
DATA_URLS = [
    "https://raw.githubusercontent.com/first2022-cyber/contents/main/population_ts_yearly_gender.zip",
    "https://raw.githubusercontent.com/doyun308/population/main/population_ts_yearly_gender.zip",
]

# 핵심: 0세부터 100세 이상까지 '나이 순서'를 직접 정의합니다.
AGES = [f"{age}세" for age in range(100)] + ["100세 이상"]
MALE_COLUMNS = [f"남_{age}" for age in AGES]
FEMALE_COLUMNS = [f"여_{age}" for age in AGES]
REQUIRED_COLUMNS = ["연도", "시도", "시군구", "동"] + MALE_COLUMNS + FEMALE_COLUMNS


# 2. ZIP에 들어 있는 CSV를 읽고, 가장 최신 연도만 남깁니다.
# 캐시 덕분에 드롭다운을 바꿀 때마다 파일을 다시 내려받지 않습니다.
@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def load_latest_data():
    errors = []

    for url in DATA_URLS:
        # 원본 CSV 파일의 한글 인코딩 차이에 대비합니다.
        for encoding in ["utf-8-sig", "cp949"]:
            try:
                newest_year = None
                newest_chunks = []

                # 파일 전체를 한꺼번에 처리하지 않고 조각으로 읽습니다.
                reader = pd.read_csv(
                    url,
                    compression="zip",
                    encoding=encoding,
                    chunksize=5000,
                    low_memory=False,
                )

                for chunk in reader:
                    chunk.columns = chunk.columns.astype(str).str.strip()
                    missing = [c for c in REQUIRED_COLUMNS if c not in chunk.columns]
                    if missing:
                        raise ValueError("필요한 열 누락: " + ", ".join(missing[:8]))

                    years = pd.to_numeric(chunk["연도"], errors="coerce")
                    chunk_year = years.max()
                    if pd.isna(chunk_year):
                        continue

                    # 더 최신인 연도가 나오면 예전 연도는 버립니다.
                    if newest_year is None or chunk_year > newest_year:
                        newest_year = int(chunk_year)
                        newest_chunks = [chunk.loc[years == chunk_year].copy()]
                    elif int(chunk_year) == newest_year:
                        newest_chunks.append(chunk.loc[years == newest_year].copy())

                if not newest_chunks:
                    raise ValueError("연도 데이터가 없습니다.")

                latest = pd.concat(newest_chunks, ignore_index=True)

                for col in ["시도", "시군구", "동"]:
                    latest[col] = latest[col].fillna("").astype(str).str.strip()

                # 이름이 비어 있는 합계 행 등은 선택 목록에서 제외합니다.
                latest = latest.loc[
                    (latest["시도"] != "")
                    & (latest["시군구"] != "")
                    & (latest["동"] != "")
                ].copy()

                if latest.empty:
                    raise ValueError("선택 가능한 동네가 없습니다.")

                return latest, newest_year, url

            except Exception as exc:
                errors.append(f"{url} ({encoding}): {exc}")

    raise RuntimeError("CSV 파일을 읽지 못했습니다.\n" + "\n".join(errors))


# 3. 하나의 동네에서 나이별 인구를 더합니다.
def sum_by_age(rows, column_names):
    # '1,234'처럼 쉼표가 있는 숫자도 정상적으로 변환합니다.
    numeric_table = (
        rows[column_names]
        .astype(str)
        .replace(",", "", regex=True)
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
    )
    # 해당 지역의 행이 여러 개면 같은 나이끼리 합산합니다.
    return [int(value) for value in numeric_table.sum(axis=0).tolist()]


# 4. 연령별 인구로 평균연령, 아동 비율, 고령화율 등을 계산합니다.
def calculate_statistics(age_counts):
    total = sum(age_counts)
    children = sum(age_counts[:15])     # 0~14세
    working_age = sum(age_counts[15:65])  # 15~64세
    seniors = sum(age_counts[65:])      # 65세 이상

    # 100세 이상은 정확한 나이를 알 수 없으므로 100세로 간주합니다.
    # 따라서 이 수치는 '정확한 평균연령'이 아닌 '추정 평균연령'입니다.
    weighted_age_sum = sum(
        age * count for age, count in enumerate(age_counts)
    )
    average_age = weighted_age_sum / total if total else None

    child_rate = children / total * 100 if total else 0.0
    senior_rate = seniors / total * 100 if total else 0.0

    # 추가 기능: 노령화지수 = 65세 이상 / 0~14세 * 100
    # 유소년 인구가 0명이면 나누기할 수 없으므로 None으로 처리합니다.
    aging_index = seniors / children * 100 if children else None

    return {
        "total": total,
        "children": children,
        "working_age": working_age,
        "seniors": seniors,
        "average_age": average_age,
        "child_rate": child_rate,
        "senior_rate": senior_rate,
        "aging_index": aging_index,
    }


# 5. 피라미드 아래에 표시할 한 줄 설명을 자동으로 만듭니다.
def describe_neighborhood(stats):
    if stats["total"] == 0:
        return "인구가 0명으로 집계되어 아이와 어르신의 비중을 비교할 수 없습니다."

    children = stats["children"]
    seniors = stats["seniors"]
    child_rate = stats["child_rate"]
    senior_rate = stats["senior_rate"]

    if children > seniors:
        conclusion = "아이(0~14세)가 어르신(65세 이상)보다 많습니다."
    elif seniors > children:
        conclusion = "어르신(65세 이상)이 아이(0~14세)보다 많습니다."
    else:
        conclusion = "아이와 어르신의 인구수가 같습니다."

    return (
        f"{conclusion} "
        f"(아이 {child_rate:.1f}% · 어르신 {senior_rate:.1f}%)"
    )


# 6. Plotly 가로 막대 인구 피라미드를 생성합니다.
def create_pyramid(male_counts, female_counts, total_population, percent_mode):
    if percent_mode:
        denominator = total_population if total_population else 1
        males_x = [-100 * count / denominator for count in male_counts]
        females_x = [100 * count / denominator for count in female_counts]
    else:
        males_x = [-count for count in male_counts]
        females_x = list(female_counts)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=males_x,
            y=AGES,
            orientation="h",
            name="남성",
            marker_color="#7ca7ca",
            customdata=male_counts,
            hovertemplate="남성 · %{y}<br>%{customdata:,}명<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=females_x,
            y=AGES,
            orientation="h",
            name="여성",
            marker_color="#ec9c8d",
            customdata=female_counts,
            hovertemplate="여성 · %{y}<br>%{customdata:,}명<extra></extra>",
        )
    )

    # 양쪽 막대의 범위를 동일하게 설정해 남녀 인구를 공정하게 비교합니다.
    maximum = max([abs(v) for v in males_x + females_x] + [0.1])
    bound = maximum * 1.12
    tick_positions = [-bound, -bound / 2, 0, bound / 2, bound]

    if percent_mode:
        tick_labels = [f"{abs(v):.1f}%" for v in tick_positions]
        x_title = "전체 인구 대비 비율 (%)"
    else:
        tick_labels = [f"{abs(v):,.0f}" for v in tick_positions]
        x_title = "인구수 (명)"

    fig.update_layout(
        height=1320,
        barmode="relative",
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",
        font=dict(
            family="Malgun Gothic, Apple SD Gothic Neo, sans-serif",
            color="#624d43",
        ),
        margin=dict(l=70, r=35, t=50, b=55),
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
            tickvals=tick_positions,
            ticktext=tick_labels,
            gridcolor="#f1e7da",
            zeroline=True,
            zerolinecolor="#ae9586",
            zerolinewidth=2,
        ),
        yaxis=dict(
            title="나이",
            type="category",
            # 순서를 자동정렬하거나 축을 뒤집지 않습니다.
            # 0세 → 100세 이상 순서를 직접 고정합니다.
            categoryorder="array",
            categoryarray=AGES,
            # Plotly에서 첫 범주가 아래, 마지막 범주가 위에 오도록 설정합니다.
            range=[-0.5, len(AGES) - 0.5],
            tickmode="array",
            tickvals=AGES[::10],
            ticktext=AGES[::10],
            showgrid=False,
        ),
    )

    # 0세가 아래, 100세 이상이 위라는 조건을 코드로 검증합니다.
    assert fig.layout.yaxis.categoryarray[0] == "0세"
    assert fig.layout.yaxis.categoryarray[-1] == "100세 이상"
    assert fig.layout.yaxis.range[0] < fig.layout.yaxis.range[1]
    return fig


# 7. 앱 상단의 제목 및 지역 선택 화면
st.title("🏘️ 동네별 인구 피라미드")
st.write("전국 읍·면·동을 선택해 연령별 인구 분포와 고령화 정도를 살펴보세요.")

try:
    with st.spinner("최신 연도 인구 데이터를 불러오는 중입니다..."):
        data, latest_year, data_url = load_latest_data()
except Exception as exc:
    st.error("인구 데이터를 불러올 수 없습니다. ZIP 파일 주소와 CSV 열 이름을 확인해 주세요.")
    with st.expander("오류 자세히 보기"):
        st.code(str(exc))
    st.stop()

st.caption(f"📅 자료에 포함된 최신 연도: **{latest_year}년**")

col1, col2, col3 = st.columns(3)
with col1:
    province = st.selectbox("① 시도 선택", sorted(data["시도"].unique()))

province_rows = data.loc[data["시도"] == province]
with col2:
    district = st.selectbox("② 시군구 선택", sorted(province_rows["시군구"].unique()))

district_rows = province_rows.loc[province_rows["시군구"] == district]
with col3:
    neighborhood = st.selectbox("③ 읍·면·동 선택", sorted(district_rows["동"].unique()))

selected_rows = district_rows.loc[district_rows["동"] == neighborhood]
male = sum_by_age(selected_rows, MALE_COLUMNS)
female = sum_by_age(selected_rows, FEMALE_COLUMNS)
all_ages = [m + f for m, f in zip(male, female)]

male_total = sum(male)
female_total = sum(female)
stats = calculate_statistics(all_ages)

st.subheader(f"📍 {province} {district} {neighborhood}")

# 상세 표와 다운로드에도 그래프와 동일한 숫자를 사용합니다.
detail_table = pd.DataFrame(
    {"나이": AGES, "남성(명)": male, "여성(명)": female, "전체(명)": all_ages}
)
detail_table["전체 대비 비율(%)"] = (
    (detail_table["전체(명)"] / stats["total"] * 100).round(2)
    if stats["total"]
    else 0.0
)

pyramid_tab, groups_tab, table_tab = st.tabs(
    ["📊 인구 피라미드", "🧒 연령대별 분석", "📥 상세 표·다운로드"]
)

# 8. 인구 피라미드 탭
with pyramid_tab:
    # 요청한 3개 지표 카드: 총인구, 평균연령, 고령화율
    card1, card2, card3 = st.columns(3)

    with card1:
        st.metric("👥 총인구", f"{stats['total']:,}명")

    with card2:
        avg_age_text = (
            f"{stats['average_age']:.1f}세"
            if stats["average_age"] is not None
            else "자료 없음"
        )
        st.metric("🎂 평균연령(추정)", avg_age_text)

    with card3:
        # 정확히 '20%를 넘는' 동네에만 경고를 표시합니다.
        high_aging = stats["total"] > 0 and stats["senior_rate"] > 20
        aging_label = "👵 고령화율 ⚠️ 주의" if high_aging else "👵 고령화율"
        st.metric(aging_label, f"{stats['senior_rate']:.1f}%")
        if high_aging:
            st.caption("⚠️ 65세 이상 인구 비율이 20%를 초과합니다.")

    if stats["total"] == 0:
        st.warning("선택한 지역의 인구가 0명으로 집계되었습니다. 원본 데이터를 확인하세요.")

    show_mode = st.radio(
        "그래프 표시 방식",
        ["인구수(명)", "인구 비율(%)"],
        horizontal=True,
    )
    percent_mode = show_mode == "인구 비율(%)"

    st.plotly_chart(
        create_pyramid(male, female, stats["total"], percent_mode),
        use_container_width=True,
        config={"displaylogo": False},
    )

    # 요청한 자동 한 줄 설명 (해당 동네 안에서 두 연령층을 비교합니다).
    st.info(
        "💡 이 동네는 아이가 많은 편인가요, 어르신이 많은 편인가요? "
        + describe_neighborhood(stats)
    )
    st.caption(
        "남성은 왼쪽, 여성은 오른쪽입니다. 맨 아래는 0세, 맨 위는 100세 이상입니다. "
        "자동 설명은 전국 평균이 아니라 이 동네의 0~14세와 65세 이상을 비교한 결과입니다."
    )

# 9. 연령대별 분석 탭
with groups_tab:
    groups = ["0~14세 (유소년)", "15~64세 (생산연령)", "65세 이상 (고령)"]
    group_counts = [stats["children"], stats["working_age"], stats["seniors"]]
    group_table = pd.DataFrame(
        {
            "연령대": groups,
            "인구수(명)": group_counts,
            "전체 대비 비율(%)": [
                round(count / stats["total"] * 100, 1) if stats["total"] else 0
                for count in group_counts
            ],
        }
    )
    st.dataframe(group_table, hide_index=True, use_container_width=True)

    # 추가 기능: 노령화지수 (유소년 100명당 고령인구 수)
    index_label = (
        f"{stats['aging_index']:.1f}명"
        if stats["aging_index"] is not None
        else "계산 불가"
    )
    st.metric("📌 노령화지수 (유소년 100명당 고령인구)", index_label)
    st.caption("노령화지수 = (65세 이상 인구 ÷ 0~14세 인구) × 100")

    if stats["total"] > 0:
        donut = go.Figure(
            go.Pie(
                labels=groups,
                values=group_counts,
                hole=0.55,
                marker=dict(colors=["#e9bd74", "#8bb4aa", "#d49487"]),
                textinfo="label+percent",
                hovertemplate="%{label}: %{value:,}명 (%{percent})<extra></extra>",
            )
        )
        donut.update_layout(
            height=400,
            margin=dict(l=15, r=15, t=20, b=20),
            paper_bgcolor="#fff9f0",
            font=dict(family="Malgun Gothic, sans-serif"),
            showlegend=False,
        )
        st.plotly_chart(donut, use_container_width=True, config={"displaylogo": False})

        most_common_age = max(range(len(all_ages)), key=lambda i: all_ages[i])
        st.info(
            f"가장 인구가 많은 나이는 **{AGES[most_common_age]}**이며 "
            f"**{all_ages[most_common_age]:,}명**입니다. "
            f"(남성 {male_total:,}명 · 여성 {female_total:,}명)"
        )

    st.caption(
        "평균연령은 개별 연령별 인구로 가중평균해 계산했습니다. "
        "'100세 이상' 구간은 모두 100세로 간주하므로 추정치입니다."
    )

# 10. 나이별 상세 데이터 및 다운로드 탭
with table_tab:
    st.dataframe(detail_table, hide_index=True, use_container_width=True, height=520)
    csv_data = detail_table.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 선택한 동네의 CSV 다운로드",
        data=csv_data,
        file_name=(
            f"인구피라미드_{latest_year}_{province}_{district}_{neighborhood}.csv"
        ),
        mime="text/csv",
    )
    st.caption("CSV는 엑셀에서도 한글이 보이도록 UTF-8(BOM)으로 저장됩니다.")

st.divider()
st.caption(
    f"출처: 제공된 GitHub 인구자료 ({latest_year}년) · "
    "고령화율 = 65세 이상 인구 ÷ 총인구 × 100"
)
