"""BKT 参数个性化拟合（Baum-Welch EM）。

借鉴 Tutor-Forge fit_em：对每个知识点用历史答题序列拟合 4 个参数
（P(L0) 先验、P(T) 学习转移、P(G) 猜对、P(S) 失误），替代固定默认值。
Guess/Slip 做 clipping 防止退化。数据不足时回退全局默认。
"""
import json
import math
from . import db

# 全局默认参数（与 defects.py / quiz_grade 保持一致）
DEFAULT_P_L0 = 0.3
DEFAULT_P_T = 0.13
DEFAULT_P_G_CHOICE = 0.25   # 选择/判断
DEFAULT_P_G_OPEN = 0.05     # 简答
DEFAULT_P_S = 0.10

# EM clipping 边界
_MAX_GUESS = 0.35
_MAX_SLIP = 0.25
_MIN_ATTEMPTS = 10          # 少于此条数不做个性化拟合


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _bkt_posterior(p_l: float, correct: bool, p_g: float, p_s: float) -> float:
    """单步贝叶斯后验更新 P(L|obs)。"""
    if correct:
        num = p_l * (1 - p_s)
        den = num + (1 - p_l) * p_g
    else:
        num = p_l * p_s
        den = num + (1 - p_l) * (1 - p_g)
    return num / den if den > 1e-12 else p_l


def _bkt_predict_correct(p_l: float, p_g: float, p_s: float) -> float:
    """预测下一次答对的概率。"""
    return p_l * (1 - p_s) + (1 - p_l) * p_g


def fit_em(
    observations: list[bool],
    n_iters: int = 50,
    p_l0_init: float = 0.3,
    p_t_init: float = 0.13,
    p_g_init: float = 0.15,
    p_s_init: float = 0.10,
) -> dict:
    """对单个知识点的答题序列做 Baum-Welch EM 拟合。

    observations: True=答对, False=答错，按时间顺序。
    返回 {"p_l0","p_t","p_g","p_s","log_likelihood","n"}。
    """
    n = len(observations)
    if n < 2:
        return {
            "p_l0": p_l0_init, "p_t": p_t_init,
            "p_g": p_g_init, "p_s": p_s_init,
            "log_likelihood": None, "n": n,
        }

    p_l0, p_t, p_g, p_s = p_l0_init, p_t_init, p_g_init, p_s_init

    for _ in range(n_iters):
        # ---- E-step: forward-backward ----
        # forward: alpha[t][k] = P(obs_0..t, state_t=k)
        # 状态 0=未掌握, 1=已掌握；吸收态：一旦掌握保持掌握（含学习转移）
        alpha = [[0.0, 0.0] for _ in range(n)]
        # t=0
        p_correct_if_L = [(1 - p_g), (1 - p_s)]  # state 0: guess only; state 1: no-slip
        p_obs0 = [p_g if observations[0] else (1 - p_g),
                  (1 - p_s) if observations[0] else p_s]
        alpha[0][0] = (1 - p_l0) * p_obs0[0]
        alpha[0][1] = p_l0 * p_obs0[1]
        for t in range(1, n):
            # transition: 0→0: 1-p_t, 0→1: p_t, 1→1: 1, 1→0: 0
            a00 = alpha[t - 1][0] * (1 - p_t) + alpha[t - 1][1] * 0.0
            a01 = alpha[t - 1][0] * p_t + alpha[t - 1][1] * 1.0
            p_obs = [p_g if observations[t] else (1 - p_g),
                     (1 - p_s) if observations[t] else p_s]
            alpha[t][0] = a00 * p_obs[0]
            alpha[t][1] = a01 * p_obs[1]

        # backward: beta[t][k] = P(obs_{t+1..n-1} | state_t=k)
        beta = [[1.0, 1.0] for _ in range(n)]
        for t in range(n - 2, -1, -1):
            p_obs_next = [p_g if observations[t + 1] else (1 - p_g),
                          (1 - p_s) if observations[t + 1] else p_s]
            beta[t][0] = ((1 - p_t) * p_obs_next[0] * beta[t + 1][0] +
                          p_t * p_obs_next[1] * beta[t + 1][1])
            beta[t][1] = beta[t + 1][1] * p_obs_next[1]

        # gamma[t][k] = P(state_t=k | all obs)
        gamma = [[0.0, 0.0] for _ in range(n)]
        for t in range(n):
            s = alpha[t][0] * beta[t][0] + alpha[t][1] * beta[t][1]
            if s > 1e-12:
                gamma[t][0] = alpha[t][0] * beta[t][0] / s
                gamma[t][1] = alpha[t][1] * beta[t][1] / s

        # xi[t][i][j] = P(state_t=i, state_{t+1}=j | all obs)
        # 只需 P(0→1) 用于估计 p_t
        xi_01_sum = 0.0
        gamma_0_sum = 0.0
        for t in range(n - 1):
            p_obs_next = [p_g if observations[t + 1] else (1 - p_g),
                          (1 - p_s) if observations[t + 1] else p_s]
            # unnormalized xi(0,1)
            xi01 = (alpha[t][0] * p_t * p_obs_next[1] * beta[t + 1][1])
            s = alpha[t + 1][0] + alpha[t + 1][1]
            # normalize by total likelihood at t+1
            total = alpha[t][0] * ((1 - p_t) * p_obs_next[0] * beta[t + 1][0] +
                                   p_t * p_obs_next[1] * beta[t + 1][1]) + \
                    alpha[t][1] * p_obs_next[1] * beta[t + 1][1]
            if total > 1e-12:
                xi_01_sum += xi01 / total
            gamma_0_sum += gamma[t][0]

        # ---- M-step ----
        p_l0 = _clamp(gamma[0][1], 0.01, 0.99)
        if gamma_0_sum > 1e-9:
            p_t = _clamp(xi_01_sum / gamma_0_sum, 0.01, 0.99)

        # guess: P(obs=correct | state=0)
        num_g, den_g = 0.0, 0.0
        num_s, den_s = 0.0, 0.0
        for t in range(n):
            if observations[t]:
                num_g += gamma[t][0]
                den_s += gamma[t][1]
            else:
                den_g += gamma[t][0]
                num_s += gamma[t][1]
        if den_g + num_g > 1e-9:
            p_g = _clamp(num_g / (num_g + den_g), 0.01, _MAX_GUESS)
        if den_s + num_s > 1e-9:
            p_s = _clamp(num_s / (num_s + den_s), 0.01, _MAX_SLIP)

    # log-likelihood
    ll = 0.0
    p_l = p_l0
    for obs in observations:
        p_c = _bkt_predict_correct(p_l, p_g, p_s)
        p_obs = p_c if obs else (1 - p_c)
        ll += math.log(max(p_obs, 1e-12))
        p_l = _bkt_posterior(p_l, obs, p_g, p_s)
        p_l = p_l + (1 - p_l) * p_t  # transition

    return {
        "p_l0": round(p_l0, 4),
        "p_t": round(p_t, 4),
        "p_g": round(p_g, 4),
        "p_s": round(p_s, 4),
        "log_likelihood": round(ll, 4),
        "n": n,
    }


def _collect_observations(space_id: str, point: str) -> list[bool]:
    """从 mastery_history 收集某知识点的答题对错序列（按时间升序）。

    verdict 映射：correct→True, partial→True(弱), wrong/confused→False。
    partial 按 0.6 概率展开为对——简化为直接 True。
    """
    history = db.list_mastery_history(space_id)
    obs = []
    for h in sorted(history, key=lambda x: x["created_at"]):
        if h["point"] != point:
            continue
        v = h.get("verdict", "")
        if v in ("correct", "progress"):
            obs.append(True)
        elif v in ("wrong", "confused"):
            obs.append(False)
        elif v == "partial":
            obs.append(True)  # 部分对算弱正确
    return obs


def fit_for_space(space_id: str) -> dict:
    """对空间内所有有足够答题记录的知识点做个性化拟合。

    返回 {point: params_dict, ...}，并持久化到 meta 表。
    """
    mastery_list = db.list_mastery(space_id)
    fitted: dict[str, dict] = {}
    for m in mastery_list:
        point = m["point"]
        obs = _collect_observations(space_id, point)
        if len(obs) < _MIN_ATTEMPTS:
            continue
        params = fit_em(obs)
        fitted[point] = params
    if fitted:
        db.set_meta(f"bkt_params:{space_id}", json.dumps(fitted, ensure_ascii=False))
    return fitted


def get_params(space_id: str, point: str, qtype: str = "") -> dict:
    """获取某知识点的 BKT 参数：优先个性化拟合值，否则全局默认。"""
    raw = db.get_meta(f"bkt_params:{space_id}")
    if raw:
        try:
            all_params = json.loads(raw)
            if point in all_params:
                p = all_params[point]
                return {
                    "p_l0": p["p_l0"], "p_t": p["p_t"],
                    "p_g": p["p_g"], "p_s": p["p_s"],
                    "source": "fitted",
                }
        except (json.JSONDecodeError, KeyError):
            pass
    # 默认：按题型区分 guess
    guess = DEFAULT_P_G_CHOICE if qtype in ("选择", "判断") else DEFAULT_P_G_OPEN
    return {
        "p_l0": DEFAULT_P_L0, "p_t": DEFAULT_P_T,
        "p_g": guess, "p_s": DEFAULT_P_S,
        "source": "default",
    }


def update_mastery_bkt(space_id: str, point: str, correct: bool, qtype: str = "") -> float:
    """用（可能个性化的）BKT 参数更新掌握度，返回新的 P(L)。

    与 defects.py 的 BKT 更新兼容，但优先使用拟合参数。
    """
    params = get_params(space_id, point, qtype)
    row = db.get_mastery_point(space_id, point)
    p_l = row["score"] if row else params["p_l0"]
    # 后验更新
    p_l = _bkt_posterior(p_l, correct, params["p_g"], params["p_s"])
    # 学习转移
    p_l = p_l + (1 - p_l) * params["p_t"]
    return _clamp(p_l, 0.0, 1.0)
