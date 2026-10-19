
# 선택한 동네의 실제 데이터가 있는 연도만 표시
selected_years = sorted(
    selected_history["연도"].unique().tolist()
)

# 연도 슬라이더
year = st.select_slider(
    "📅 연도 이동",
    options=selected_years,
    value=selected_years[-1],
)

# 선택 연도의 남녀 인구와 통계 계산
male, female = ages_for_year(
    selected_history, year
)
stat = statistics(male, female)

# 지표 카드 및 피라미드 표시
show_cards(stat)

st.plotly_chart(
    pyramid_chart(male, female),
    use_container_width=True,
)
