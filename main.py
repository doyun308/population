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
    return data.loc[
        (data["시도"] == sido)
        & (data["시군구"] == sigungu)
        & (data["동"] == dong)
    ]


def ages_for_year(place_data, year):
    """한 연도의 남녀 101개 나이별 인구를 구합니다."""
    selected = place_data.loc[place_data["연도"] == year]
    if selected.empty:
        return None
    male = selected[MALE_COLS].sum(axis=0).astype(int).tolist()
    female = selected[FEMALE_COLS].sum(axis=0).astype(int).tolist()
    return male, female


def statistics(male, female):
    """지표 카드, 연령대 분석에 공통으로 쓰는 통계값입니다."""
    counts = [m + f for m, f in zip(male, female)]
    total = sum(counts)
    kids = sum(counts[:15])
    seniors = sum(counts[65:])
    return {
        "total": total,
        "male": sum(male),
        "female": sum(female),
        "kids": kids,
        "working": sum(counts[15:65]),
        "seniors": seniors,
        "kid_rate": kids / total * 100 if total else 0,
        "senior_rate": seniors / total * 100 if total else 0,
        # 100세 이상은 실제 나이를 알 수 없어 100세로 계산한 추정치입니다.
        "avg_age": sum(a * n for a, n in zip(AGE_VALUES, counts)) / total if total else None,
        "aging_index": seniors / kids * 100 if kids else None,
        "counts": counts,
    }


def pyramid_chart(male, female, percent=False, common_bound=None, height=1150):
    """남자는 왼쪽, 여자는 오른쪽. 나이 눈금의 위아래를 고정합니다."""
    total = sum(male) + sum(female)
    divisor = total if total else 1
    left = [-m * (100 / divisor if percent else 1) for m in male]
    right = [f * (100 / divisor if percent else 1) for f in female]

    fig = go.Figure()
    fig.add_bar(
        x=left, y=AGES, name="남성", orientation="h",
        marker_color="#77a9c8", customdata=male,
        hovertemplate="남성 · %{y}<br>%{customdata:,}명<extra></extra>",
    )
    fig.add_bar(
        x=right, y=AGES, name="여성", orientation="h",
        marker_color="#e99e95", customdata=female,
        hovertemplate="여성 · %{y}<br>%{customdata:,}명<extra></extra>",
    )
    bound = common_bound or max([abs(v) for v in left + right] + [0.1]) * 1.15
    ticks = [-bound, -bound / 2, 0, bound / 2, bound]
    labels = [f"{abs(v):.1f}%" if percent else f"{abs(v):,.0f}" for v in ticks]
    fig.update_layout(
        barmode="relative", height=height,
        paper_bgcolor="#fffdf8", plot_bgcolor="#fffdf8",
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif", color="#624d43"),
        margin=dict(l=60, r=25, t=48, b=52),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1.03, yanchor="bottom"),
        xaxis=dict(
            title="전체 인구 대비 비율 (%)" if percent else "인구수 (명)",
            range=[-bound, bound], tickmode="array", tickvals=ticks, ticktext=labels,
            gridcolor="#f0e5d8", zeroline=True, zerolinecolor="#9f8a7b",
        ),
        yaxis=dict(
            title="나이", type="category",
            # 첫 범주가 아래, 마지막 범주가 위: 뒤집기/값 정렬 옵션은 사용하지 않습니다.
            categoryorder="array", categoryarray=AGES,
            range=[-0.5, 100.5],
            tickmode="array", tickvals=AGES[::10], ticktext=AGES[::10],
        ),
    )
    # 가장 아래가 0세, 가장 위가 100세 이상인지 검증합니다.
    assert fig.layout.yaxis.categoryarray[0] == "0세"
    assert fig.layout.yaxis.categoryarray[-1] == "100세 이상"
    assert fig.layout.yaxis.range[0] < fig.layout.yaxis.range[1]
    return fig


def place_selector(data, prefix="main", reference=None):
    """시도→시군구→동 3단계 연결 드롭다운입니다."""
    columns = st.columns(3)
    sido_options = sorted(data["시도"].unique().tolist())
    default_sido = (sido_options.index(reference[0]) if reference and reference[0] in sido_options else 0)
    with columns[0]:
        sido = st.selectbox("① 시도", sido_options, index=default_sido, key=prefix + "_sido")

    filtered = data.loc[data["시도"] == sido]
    gun_options = sorted(filtered["시군구"].unique().tolist())
    default_gun = (gun_options.index(reference[1]) if reference and reference[1] in gun_options else 0)
    with columns[1]:
        gun = st.selectbox("② 시군구", gun_options, index=default_gun, key=prefix + "_gun")

    dong_options = sorted(filtered.loc[filtered["시군구"] == gun, "동"].unique().tolist())
    default_dong = (dong_options.index(reference[2]) if reference and reference[2] in dong_options else 0)
    with columns[2]:
        dong = st.selectbox("③ 읍·면·동", dong_options, index=default_dong, key=prefix + "_dong")
    return sido, gun, dong


def show_cards(stat):
    """요청한 세 개 지표를 나란히 보여줍니다."""
    a, b, c = st.columns(3)
    a.metric("👥 총인구", f"{stat['total']:,}명")
    b.metric("🎂 평균연령(추정)", f"{stat['avg_age']:.1f}세" if stat["avg_age"] is not None else "자료 없음")
    caution = stat["total"] > 0 and stat["senior_rate"] > 20
    c.metric("👵 고령화율" + (" ⚠️ 주의" if caution else ""), f"{stat['senior_rate']:.1f}%")
    if caution:
        st.warning("⚠️ 이 지역은 65세 이상 인구가 전체의 20%를 초과합니다.")


def explain(stat):
    """아이와 어르신 중 어느 쪽이 많은지 한 줄로 설명합니다."""
    if stat["total"] == 0:
        return "인구가 0명으로 집계되어 비교할 수 없습니다."
    if stat["kids"] > stat["seniors"]:
        outcome = "아이(0~14세)가 어르신(65세 이상)보다 많습니다."
    elif stat["kids"] < stat["seniors"]:
        outcome = "어르신(65세 이상)이 아이(0~14세)보다 많습니다."
    else:
        outcome = "아이와 어르신 인구가 같습니다."
    return f"{outcome} (아이 {stat['kid_rate']:.1f}% · 어르신 {stat['senior_rate']:.1f}%)"


def history_table(place_data):
    """지역에 실제로 자료가 있는 연도만 연도별 추세로 만듭니다."""
    records = []
    for year in sorted(place_data["연도"].unique().tolist()):
        age_data = ages_for_year(place_data, year)
        if age_data is None:
            continue
        stat = statistics(*age_data)
        records.append({
            "연도": year, "총인구": stat["total"],
            "평균연령(추정)": round(stat["avg_age"], 1) if stat["avg_age"] is not None else None,
            "아동 비율(%)": round(stat["kid_rate"], 2),
            "고령화율(%)": round(stat["senior_rate"], 2),
            "0~14세(명)": stat["kids"], "65세 이상(명)": stat["seniors"],
        })
    return pd.DataFrame(records)


def age_table(male, female):
    total = sum(male) + sum(female)
    return pd.DataFrame({
        "나이": AGES, "남성(명)": male, "여성(명)": female,
        "전체(명)": [m + f for m, f in zip(male, female)],
        "전체 대비 비율(%)": [round((m + f) * 100 / total, 2) if total else 0 for m, f in zip(male, female)],
    })


def download_table(table, filename, label="📥 CSV 다운로드"):
    st.download_button(
        label, data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename, mime="text/csv",
    )


def main():
    st.set_page_config(page_title="우리 동네 인구 타임머신", page_icon="🏘️", layout="wide")
    st.markdown("""
    <style>
    .stApp { background: #fff9f0; }
    .block-container { max-width: 1250px; padding-top: 1.6rem; }
    h1, h2, h3 { color: #654e40; }
    div[data-testid="stMetric"] {
      border: 1px solid #efdfc9; background: #fffdf9;
      border-radius: 14px; padding: 14px;
    }
    </style>""", unsafe_allow_html=True)

    st.title("🏘️ 우리 동네 인구 타임머신")
    st.write("연도별 인구 피라미드, 두 지역 비교, 고령화 변화까지 한 번에 분석합니다.")

    try:
        with st.spinner("전국 인구 데이터를 읽고 있습니다. 처음 열 때만 시간이 걸릴 수 있습니다."):
            data, years, url = load_data()
    except Exception as exc:
        st.error("데이터를 불러오지 못했습니다. GitHub ZIP 주소와 열 이름을 확인하세요.")
        with st.expander("오류 내용"):
            st.code(str(exc))
        st.stop()

    st.caption(f"자료가 있는 연도: **{years[0]}~{years[-1]}년** · 최신: {years[-1]}년")
    place = place_selector(data)
    place_text = " ".join(place)
    selected_history = rows_for_place(data, place)
    selected_years = sorted(selected_history["연도"].unique().tolist())

    tab_time, tab_compare, tab_trend, tab_data = st.tabs([
        "⏳ 인구 타임머신", "⚖️ 두 동네 비교", "📈 고령화 변화", "📥 상세 데이터",
    ])

    with tab_time:
        st.subheader(f"⏳ {place_text}의 인구 타임머신")
        year = st.select_slider("📅 연도 이동", options=selected_years, value=selected_years[-1])
        male, female = ages_for_year(selected_history, year)
        stat = statistics(male, female)
        show_cards(stat)
        mode = st.radio("그래프 표시", ["인구수", "인구 비율(%)"], horizontal=True, key="time_mode")
        st.plotly_chart(pyramid_chart(male, female, mode != "인구수"), use_container_width=True)
        st.info("💡 이 동네는 아이가 많은 편인가요, 어르신이 많은 편인가요? " + explain(stat))
        st.caption("맨 아래 0세 · 맨 위 100세 이상 / 남성 왼쪽 · 여성 오른쪽")

        # 타임머신에서도 선택한 연도의 연령별 데이터를 다운로드할 수 있습니다.
        download_table(age_table(male, female), f"{place_text.replace(' ', '_')}_{year}_인구.csv", "📥 이 연도의 연령별 인구 저장")

    with tab_compare:
        st.subheader("⚖️ 두 동네 인구 비교")
        st.caption("왼쪽은 화면 위에서 선택한 동네입니다. 오른쪽 비교 동네를 골라주세요.")
        # 시작할 때는 같은 시군구의 다른 동네를 자동으로 제안합니다.
        candidates = sorted(
            data.loc[
                (data["시도"] == place[0]) & (data["시군구"] == place[1]),
                "동",
            ].unique().tolist()
        )
        alternatives = [dong for dong in candidates if dong != place[2]]
        suggestion = (place[0], place[1], alternatives[0]) if alternatives else place
        other_place = place_selector(data, prefix="compare", reference=suggestion)
        other_rows = rows_for_place(data, other_place)
        common_years = sorted(set(selected_years) & set(other_rows["연도"].unique().tolist()))
        if not common_years:
            st.warning("두 지역에 공통으로 존재하는 연도가 없어 비교할 수 없습니다.")
        else:
            comparison_year = st.select_slider("비교할 연도", options=common_years, value=common_years[-1], key="comparison_year")
            mode_comp = st.radio("비교 기준", ["인구수", "인구 비율(%)"], horizontal=True, key="comp_mode")
            ml, fl = ages_for_year(selected_history, comparison_year)
            mr, fr = ages_for_year(other_rows, comparison_year)
            sl, sr = statistics(ml, fl), statistics(mr, fr)
            comp_table = pd.DataFrame({
                "지표": ["총인구(명)", "평균연령(추정, 세)", "고령화율(%)", "아동 비율(%)"],
                "지역 A": [sl["total"], round(sl["avg_age"], 1) if sl["avg_age"] is not None else None, round(sl["senior_rate"], 1), round(sl["kid_rate"], 1)],
                "지역 B": [sr["total"], round(sr["avg_age"], 1) if sr["avg_age"] is not None else None, round(sr["senior_rate"], 1), round(sr["kid_rate"], 1)],
            })
            st.dataframe(comp_table, hide_index=True, use_container_width=True)
            # 두 그래프 모두 같은 눈금 범위를 사용해 시각적으로 공정하게 비교합니다.
            percent = mode_comp != "인구수"
            def max_width(m, f):
                factor = 100 / max(sum(m) + sum(f), 1) if percent else 1
                return max(m + f + [0.1]) * factor
            bound = max(max_width(ml, fl), max_width(mr, fr)) * 1.15
            left, right = st.columns(2)
            with left:
                st.markdown("**A · " + place_text + "**")
                st.plotly_chart(pyramid_chart(ml, fl, percent, bound, height=1050), use_container_width=True, key="chart_a")
            with right:
                st.markdown("**B · " + " ".join(other_place) + "**")
                st.plotly_chart(pyramid_chart(mr, fr, percent, bound, height=1050), use_container_width=True, key="chart_b")
            st.caption("동일 연도의 동일 축 척도로 비교합니다. 지역 경계가 달라진 경우 수치 비교에 주의하세요.")

    with tab_trend:
        st.subheader(f"📈 {place_text}의 인구 변화")
        trend = history_table(selected_history)
        if trend.empty:
            st.warning("추세를 분석할 데이터가 없습니다.")
        else:
            st.dataframe(trend, hide_index=True, use_container_width=True)
            fig = go.Figure()
            fig.add_scatter(x=trend["연도"], y=trend["아동 비율(%)"], name="아이(0~14세)", mode="lines+markers", line_color="#d5a14c")
            fig.add_scatter(x=trend["연도"], y=trend["고령화율(%)"], name="어르신(65세 이상)", mode="lines+markers", line_color="#c97f77")
            fig.add_hline(y=20, line_dash="dot", line_color="#a46d68", annotation_text="고령화율 참고선 20%")
            fig.update_layout(
                title="아동 비율과 고령화율 변화", height=390,
                xaxis=dict(title="연도", tickmode="array", tickvals=trend["연도"].tolist()),
                yaxis=dict(title="전체 인구 대비 비율 (%)", rangemode="tozero"),
                paper_bgcolor="#fffdf8", plot_bgcolor="#fffdf8", legend=dict(orientation="h"),
            )
            st.plotly_chart(fig, use_container_width=True)
            total_fig = go.Figure(go.Bar(x=trend["연도"].astype(str), y=trend["총인구"], marker_color="#8db3a9"))
            total_fig.update_layout(title="연도별 총인구", height=320, xaxis_title="연도", yaxis_title="명", paper_bgcolor="#fffdf8", plot_bgcolor="#fffdf8")
            st.plotly_chart(total_fig, use_container_width=True)
            if len(trend) >= 2:
                before, after = trend.iloc[0], trend.iloc[-1]
                st.info(
                    f"📌 {int(before['연도'])}년 → {int(after['연도'])}년: "
                    f"인구 {int(after['총인구'] - before['총인구']):+,}명, "
                    f"고령화율 {after['고령화율(%)'] - before['고령화율(%)']:+.2f}%p 변화"
                )
            download_table(trend, f"{place_text.replace(' ', '_')}_연도별_변화.csv", "📥 연도별 변화 CSV 저장")

    with tab_data:
        st.subheader("📥 상세 데이터와 연령대 분석")
        chosen_year = st.selectbox("연도", selected_years, index=len(selected_years) - 1, key="table_year")
        m, f = ages_for_year(selected_history, chosen_year)
        s = statistics(m, f)
        st.dataframe(age_table(m, f), hide_index=True, use_container_width=True, height=420)
        a, b, c = st.columns(3)
        a.metric("0~14세", f"{s['kids']:,}명")
        b.metric("15~64세", f"{s['working']:,}명")
        c.metric("65세 이상", f"{s['seniors']:,}명")
        st.metric("노령화지수 (유소년 100명당 고령인구)", f"{s['aging_index']:.1f}명" if s["aging_index"] is not None else "계산 불가")
        if s["total"]:
            # 기존 앱의 연령대별 도넛 차트도 유지합니다.
            pie = go.Figure(go.Pie(
                labels=["0~14세", "15~64세", "65세 이상"],
                values=[s["kids"], s["working"], s["seniors"]],
                hole=0.55, marker=dict(colors=["#e5b46a", "#8db3a9", "#d78f85"]),
                textinfo="label+percent",
            ))
            pie.update_layout(height=340, paper_bgcolor="#fffdf8", showlegend=False)
            st.plotly_chart(pie, use_container_width=True)
            popular_age = max(range(len(s["counts"])), key=lambda i: s["counts"][i])
            st.info(f"가장 인구가 많은 나이: **{AGES[popular_age]} ({s['counts'][popular_age]:,}명)**")
        download_table(age_table(m, f), f"{place_text.replace(' ', '_')}_{chosen_year}_상세.csv")

    st.divider()
    st.caption(
        "자료: 제공된 GitHub CSV ZIP · 평균연령은 100세 이상을 100세로 처리한 추정값 · "
        "고령화율 = (65세 이상 인구 ÷ 전체 인구) × 100 · "
        "인구 변화에는 출생·사망·이동 및 행정구역 조정이 함께 반영될 수 있습니다."
    )


if __name__ == "__main__":
    main()
