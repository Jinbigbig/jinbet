"""根据让球盘赔率和让球数，反向估算胜平负（1X2）的原始赔率。"""

def estimate_1x2_from_handicap(handicap, home_win_hcap_odds, draw_hcap_odds, away_win_hcap_odds):
    """
    从让球盘反推 1X2 赔率
    返回：(主胜赔率, 平局赔率, 客胜赔率)
    """
    # 解析让球数
    h_str = str(handicap)
    if '+' in h_str:
        h = float(h_str.replace('+', ''))  # 主队受让
    elif h_str.startswith('-'):
        h = float(h_str)  # 主队让球（负数）
    else:
        h = float(h_str)

    # 让球后的赔率转换为概率
    home_prob = 1 / float(home_win_hcap_odds) if home_win_hcap_odds else 0.33
    draw_prob = 1 / float(draw_hcap_odds) if draw_hcap_odds else 0.25
    away_prob = 1 / float(away_win_hcap_odds) if away_win_hcap_odds else 0.33
    total = home_prob + draw_prob + away_prob
    home_prob /= total
    draw_prob /= total
    away_prob /= total

    # 反推实际 1X2 概率
    if h >= 1:
        # 主队受让 h 球，客队更强
        away_actual = min(0.85, away_prob + 0.15 * h)
        home_actual = max(0.03, home_prob - 0.12 * h)
        draw_actual = max(0.05, 1 - away_actual - home_actual)
    elif h <= -1:
        # 主队让球，主队更强
        h_abs = abs(h)
        home_actual = min(0.85, home_prob + 0.15 * h_abs)
        away_actual = max(0.03, away_prob - 0.12 * h_abs)
        draw_actual = max(0.05, 1 - home_actual - away_actual)
    else:
        home_actual = home_prob
        draw_actual = draw_prob
        away_actual = away_prob

    # 归一化
    total_actual = home_actual + draw_actual + away_actual
    home_actual /= total_actual
    draw_actual /= total_actual
    away_actual /= total_actual

    # 转换为赔率（加 5% 抽水）
    margin = 1.05
    home_odds = round(margin / home_actual, 2) if home_actual > 0.01 else ''
    draw_odds = round(margin / draw_actual, 2) if draw_actual > 0.01 else ''
    away_odds = round(margin / away_actual, 2) if away_actual > 0.01 else ''

    return home_odds, draw_odds, away_odds


if __name__ == '__main__':
    # 测试：库拉索 vs 科特迪瓦（让球+2）
    h, d, a = estimate_1x2_from_handicap('+2', 2.66, 3.6, 2.1)
    print(f"库拉索 vs 科特迪瓦: 主={h} 平={d} 客={a}")

    # 突尼斯 vs 荷兰（让球+2）
    h2, d2, a2 = estimate_1x2_from_handicap('+2', 2.6, 3.5, 2.15)
    print(f"突尼斯 vs 荷兰: 主={h2} 平={d2} 客={a2}")
