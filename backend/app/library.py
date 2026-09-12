"""教材书库：预置书目 + 官方免费教材获取 + 挂载到课程空间 RAG。

版权边界：
- status=external 的书籍均为官方免费开放教材（CC 授权 / 作者官方放出的 PDF），
  pdf_url 直接指向官方站点，下载行为等价于手动从官网下载。
- status=catalog 的条目仅收录书目元数据（书名/作者/出版社），不携带任何全文内容；
  受版权保护的教材全文需用户自行以合法途径获得后，通过「上传」进入书库。

路径安全：书库内的文件一律只使用 tempfile 在上传目录内生成、
并经 realpath 前缀包含校验的路径，杜绝目录逃逸。
"""
import ipaddress
import json
import os
import shutil
import socket
import tempfile
import urllib.parse
import urllib.request

from . import db, ingest, rag
from .config import settings
from .library_example import SEED_BOOKS_EXAMPLE

ALLOWED_EXT = ingest.UPLOAD_EXTS  # PDF/PPTX/TXT/Markdown/图片/zip
MAX_BOOK_BYTES = 300 * 1024 * 1024  # 单本上限 300MB

# 预置书目：开放教材带官方直链，路线图教材只收书目信息
SEED_BOOKS = [
    # ---- 数学基础 ----
    dict(title="Linear Algebra（线性代数 · 开源教材）", author="Jim Hefferon", subject="数学基础",
         publisher="University of Vermont", license="CC BY-SA 4.0", status="external",
         pdf_url="https://jheffero.w3.uvm.edu/linearalgebra/book.pdf",
         source_url="https://hefferon.net/linearalgebra/",
         note="官方免费 PDF，覆盖同济线代全部主线，可替代考研线代基础轮教材"),
    dict(title="Convex Optimization（凸优化）", author="Stephen Boyd & Lieven Vandenberghe", subject="数学基础",
         publisher="Cambridge University Press", license="CC BY-NC-ND 4.0", status="external",
         pdf_url="https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf",
         source_url="https://web.stanford.edu/~boyd/cvxbook/",
         note="Stanford 官方免费全书，控制/运动规划优化的数学底座"),
    dict(title="Mathematics for Machine Learning", author="Deisenroth, Faisal, Ong", subject="数学基础",
         publisher="Cambridge University Press", license="官方免费 PDF", status="external",
         pdf_url="https://mml-book.github.io/book/mml-book.pdf",
         source_url="https://mml-book.github.io/",
         note="官方免费全书，线代+概率+优化的 ML 视角整合"),
    dict(title="高等数学（同济·第七版）上/下册", author="同济大学数学系", subject="数学基础",
         publisher="高等教育出版社", status="catalog",
         note="考研数学一主教材，需自备正版文件导入；配套张宇/汤家凤辅导讲义"),
    dict(title="工程数学·线性代数（同济·第六版）", author="同济大学数学系", subject="数学基础",
         publisher="高等教育出版社", status="catalog",
         note="考研线代主教材，需自备正版文件导入；配套李永乐线性代数讲义"),
    dict(title="概率论与数理统计（浙大·第五版）", author="盛骤、谢式千、潘承毅", subject="数学基础",
         publisher="高等教育出版社", status="catalog",
         note="考研概率主教材，需自备正版文件导入；配套王式安辅导讲义"),
    dict(title="Calculus（微积分 · OpenStax 全三卷）", author="OpenStax (Rice University)", subject="数学基础",
         publisher="OpenStax", license="CC BY 4.0", status="external",
         source_url="https://openstax.org/details/books/calculus-volume-1",
         note="官方免费（Volume 1-3 同页入口）；高数英文视角，配合同济版使用"),
    dict(title="Basic Analysis（实分析入门）", author="Jiří Lebl", subject="数学基础",
         publisher="Oklahoma State University", license="官方免费（OER 开放教材）", status="external",
         source_url="https://www.jirka.org/ra/",
         note="作者官网免费全书；数学分析/高数进阶，考砂数学冲高分可选读"),
    dict(title="Mathematics for Computer Science（离散数学 · MIT 6.042）", author="Lehman, Leighton, Meyer",
         subject="数学基础", publisher="MIT", license="CC BY-NC-SA（OCW 官方免费）", status="external",
         pdf_url="https://courses.csail.mit.edu/6.042/spring18/mcs.pdf",
         source_url="https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/",
         note="MIT 官方免费全书（约 10MB）；证明/图论/组合/概率，CS 数学底座"),
    dict(title="Think Stats（统计学思维 · 2e）", author="Allen B. Downey", subject="数学基础",
         publisher="Green Tea Press", license="CC BY-NC（作者官方免费）", status="external",
         pdf_url="https://greenteapress.com/thinkstats2/thinkstats2.pdf",
         source_url="https://greenteapress.com/wp/think-stats-2e/",
         note="作者官方免费全书；用 Python 讲统计，实操导向"),
    dict(title="Think Bayes（贝叶斯统计）", author="Allen B. Downey", subject="数学基础",
         publisher="Green Tea Press", license="CC BY-NC（作者官方免费）", status="external",
         pdf_url="https://greenteapress.com/thinkbayes/thinkbayes.pdf",
         source_url="https://greenteapress.com/wp/think-bayes/",
         note="作者官方免费全书；贝叶斯推断的计算视角入门"),
    dict(title="An Introduction to Statistical Learning（ISL · 含 Python 版）",
         author="James, Witten, Hastie, Tibshirani, Taylor", subject="数学基础",
         publisher="Springer", license="官方免费 PDF（作者网站放出）", status="external",
         source_url="https://www.statlearning.com/",
         note="官网免费全书（R 版与 Python 版）；统计学习最佳入门，机器学习先修"),
    dict(title="The Elements of Statistical Learning（统计学习基础 · ESL）",
         author="Hastie, Tibshirani, Friedman", subject="数学基础",
         publisher="Springer", license="官方免费 PDF（作者网站放出）", status="external",
         source_url="https://hastie.su.domains/ElemStatLearn/",
         note="作者官方免费全书（12 次印刷修正版）；统计学习圣经，ISL 的进阶版"),
    dict(title="Introduction to Probability, Statistics and Random Processes",
         author="Hossein Pishro-Nik", subject="数学基础",
         publisher="UMass Amherst", license="官方免费在线全书", status="external",
         source_url="https://www.probabilitycourse.com/",
         note="作者官网免费；概率+随机过程，信号与系统/通信/控制方向基础"),
    # ---- 物理·力学 ----
    dict(title="University Physics 三卷本（大学物理 · 开源教材）", author="OpenStax (Rice University)",
         subject="物理·力学", publisher="OpenStax", license="CC BY 4.0", status="external",
         source_url="https://openstax.org/subjects/science",
         note="官网免费下载（部分网络需代理，下载后导入）；理论力学/材料力学先修基础"),
    dict(title="Introduction to Probability（概率论 · Grinstead & Snell）", author="Charles Grinstead & J. Laurie Snell",
         subject="数学基础", publisher="Dartmouth College", license="GPL（作者官方免费）", status="external",
         pdf_url="https://math.dartmouth.edu/~chance/teaching_aids/books_articles/probability_book/book.pdf",
         source_url="https://math.dartmouth.edu/~chance/teaching_aids/books_articles/probability_book/Book.html",
         note="Dartmouth 官方免费全书（约 2MB）；比浙大版深一档，配合考研概率强化"),
    dict(title="OpenIntro Statistics（开放统计学）", author="David Diez 等", subject="数学基础",
         publisher="OpenIntro", license="CC BY-SA（官方免费）", status="external",
         source_url="https://www.openintro.org/book/os/",
         note="官网免费下载（下载页需把价格设为 $0）；统计入门，概率论之外的实用统计"),
    dict(title="Calculus（微积分 · Gilbert Strang）", author="Gilbert Strang", subject="数学基础",
         publisher="MIT / Wellesley-Cambridge", license="作者官方免费分章 PDF", status="external",
         source_url="https://math.mit.edu/~gs/calculus/",
         note="MIT Strang 教授官方免费放出的全书分章 PDF；高等数学英文视角"),
    dict(title="材料力学（第 2 版）", author="李晨、范钦珊", subject="物理·力学",
         publisher="机械工业出版社", status="catalog",
         note="路线图指定拔高教材，需自备正版文件导入"),
    dict(title="机械振动基础", author="（清华课程讲义）", subject="物理·力学",
         publisher="清华大学出版社", status="catalog",
         note="发那科动力学分析岗位相关，需自备正版文件导入"),
    dict(title="Engineering Statics（工程静力学 · 开放教材）", author="Baker, Haynes, Moore 等",
         subject="物理·力学", publisher="开放教材项目", license="CC BY-NC-SA（官方免费）", status="external",
         pdf_url="https://engineeringstatics.org/pdf/statics.pdf",
         source_url="https://engineeringstatics.org/",
         note="官方免费整本 PDF；静力学图解与受力分析，机械系列先修"),
    # ---- 机械设计（819 主线） ----
    dict(title="机械原理教程（第 3 版）", author="申永胜", subject="机械设计",
         publisher="清华大学出版社", status="catalog",
         note="819 考研「圣经」·国家级规划教材；机构结构分析、运动/力分析、齿轮凸轮连杆"),
    dict(title="机械设计", author="吴宗泽", subject="机械设计",
         publisher="清华大学出版社", status="catalog",
         note="819 第二指定教材；齿轮、轴承、轴、螺栓连接设计计算与失效分析"),
    dict(title="机械制图", author="（清华大学出版社）", subject="机械设计",
         publisher="清华大学出版社", status="catalog",
         note="配合 SolidWorks/CAD 实训，先进成图大赛备赛底子"),
    # ---- 控制与机电（822 主线） ----
    dict(title="Feedback Systems（反馈系统 · 2e）", author="Karl Johan Åström & Richard M. Murray",
         subject="控制与机电", publisher="Princeton University Press",
         license="CC BY-NC-ND（官方免费）", status="external",
         source_url="https://fbsbook.org/",
         note="控制学科经典教材，官网免费全书；控制工程基础/自控的英文进阶读物"),
    dict(title="控制工程基础（第 5 版）", author="董景新 等", subject="控制与机电",
         publisher="清华大学出版社", status="catalog",
         note="822 指定教材，配套《习题解》；需自备正版文件导入"),
    dict(title="自动控制原理", author="胡寿松", subject="控制与机电",
         publisher="科学出版社", status="catalog",
         note="经典控制深化：根轨迹、频域、PID 校正；需自备正版文件导入"),
    dict(title="机电传动控制", author="（华中科技大学出版社）", subject="控制与机电",
         publisher="华中科技大学出版社", status="catalog",
         note="发那科伺服驱动核心，配合 FOC 电机控制专题"),
    dict(title="信号与系统（第三版）", author="郑君里", subject="控制与机电",
         publisher="高等教育出版社", status="catalog",
         note="振动信号处理、伺服环路分析基础"),
    dict(title="嵌入式系统原理（STM32 实战）", author="（任选主流教材）", subject="控制与机电",
         publisher="—", status="catalog",
         note="发那科实时控制系统必备，结合 RM 实战推进电机驱动专题"),
    # ---- 机器人·智能制造 ----
    dict(title="Modern Robotics: Mechanics, Planning, and Control", author="Kevin Lynch & Frank Park",
         subject="机器人·智能制造", publisher="Cambridge University Press",
         license="官方预印本免费（作者网站放出）", status="external",
         pdf_url="https://hades.mech.northwestern.edu/images/7/7f/MR.pdf",
         source_url="https://hades.mech.northwestern.edu/",
         note="官方免费全书；DH 参数、正逆解、雅可比，发那科机器人岗位核心"),
    dict(title="Underactuated Robotics（欠驱动机器人学）", author="Russ Tedrake", subject="机器人·智能制造",
         publisher="MIT", license="官方免费（作者网站放出）", status="external",
         source_url="https://underactuated.mit.edu/",
         note="MIT 研究生级开放教材，PDF 在作者 GitHub Releases 下载；运动规划与控制进阶"),
    dict(title="智能制造概论", author="（教育部机械教指委系列教材）", subject="机器人·智能制造",
         publisher="清华大学出版社", status="catalog",
         note="智能制造系列主干教材，建立系统整体观"),
    dict(title="机器人基础", author="杨勇、谢广明", subject="机器人·智能制造",
         publisher="清华大学出版社", status="catalog",
         note="智能制造系列教材，运动学/动力学入门"),
    dict(title="协作机器人", author="陶波、赵兴炜", subject="机器人·智能制造",
         publisher="清华大学出版社", status="catalog",
         note="含 MATLAB 运动仿真与 ROS 程序"),
    dict(title="智能制造装备基础", author="（清华社系列教材）", subject="机器人·智能制造",
         publisher="清华大学出版社", status="catalog",
         note="数控技术/数字孪生专题，西门子杯「智能装备设计与数字孪生制造」赛项支撑"),
    dict(title="工业互联网基础 / 制造智能技术基础", author="（清华社系列教材）", subject="机器人·智能制造",
         publisher="清华大学出版社", status="catalog",
         note="数据采集、设备联网、智能决策"),
    # ---- 人工智能（已有 ML/DL 基础的进阶） ----
    dict(title="动手学深度学习（PyTorch 版 · 中文）", author="阿斯顿·张 等", subject="人工智能",
         publisher="人民邮电出版社", license="CC BY-NC-SA（官方免费）", status="external",
         pdf_url="https://zh-v2.d2l.ai/d2l-zh-pytorch.pdf",
         source_url="https://zh.d2l.ai/",
         note="官方免费中文全书；深度学习与模型侧知识的中文主线教材"),
    dict(title="Reinforcement Learning: An Introduction (2e)", author="Richard Sutton & Andrew Barto",
         subject="人工智能", publisher="MIT Press", license="官方免费 PDF（作者网站放出）",
         status="external",
         pdf_url="http://incompleteideas.net/book/RLbook2020.pdf",
         source_url="http://incompleteideas.net/book/the-book-2nd.html",
         note="RL 鼻祖教材官方免费全书"),
    dict(title="Think Python (2e)", author="Allen B. Downey", subject="人工智能",
         publisher="O'Reilly / Green Tea Press", license="CC BY-NC（官方免费 PDF）", status="external",
         pdf_url="https://greenteapress.com/thinkpython2/thinkpython2.pdf",
         source_url="https://greenteapress.com/wp/think-python-2e/",
         note="官方免费，Python 基础查漏补缺轻读物"),
    dict(title="Speech and Language Processing (3e draft)", author="Dan Jurafsky & James Martin",
         subject="人工智能", publisher="Stanford University", license="官方免费草稿 PDF（作者放出）", status="external",
         pdf_url="https://web.stanford.edu/~jurafsky/slp3/ed3book.pdf",
         source_url="https://web.stanford.edu/~jurafsky/slp3/",
         note="NLP 圣经最新版官方免费（约 25MB）；做大模型/Agent 的理论底座"),
    dict(title="The Little Book of Deep Learning", author="François Fleuret", subject="人工智能",
         publisher="University of Geneva", license="CC BY-NC（作者官方免费）", status="external",
         pdf_url="https://fleuret.org/public/lbdl.pdf",
         source_url="https://fleuret.org/lbdl/",
         note="官方免费小册（约 4MB），深度学习概念速查，手机排版友好"),
    dict(title="Understanding Deep Learning", author="Simon J.D. Prince", subject="人工智能",
         publisher="MIT Press", license="官方免费 PDF（作者网站放出）", status="external",
         source_url="https://udlbook.github.io/udlbook/",
         note="2023 年新书，官方免费 PDF 在作者 GitHub Releases；比 Goodfellow 更新"),
    dict(title="神经网络与深度学习（第 2 版 · 中文）", author="邱锡鹏", subject="人工智能",
         publisher="机械工业出版社", license="电子版官方开放下载", status="external",
         source_url="https://nndl.ai/nndl-v2/",
         note="国内经典中文 DL 教材，官网提供免费电子版下载"),
    dict(title="Probabilistic Machine Learning: An Introduction", author="Kevin Murphy", subject="人工智能",
         publisher="MIT Press", license="官方免费草稿 PDF（作者放出）", status="external",
         source_url="https://probml.github.io/pml-book/",
         note="官方免费草稿全书，概率视角 ML 全景；模型选型与进阶参考"),
    dict(title="Probabilistic Machine Learning: Advanced Topics", author="Kevin Murphy", subject="人工智能",
         publisher="MIT Press", license="官方免费草稿 PDF（作者放出）", status="external",
         source_url="https://probml.github.io/pml-book/",
         note="同页下册官方免费；生成模型/贝叶斯深度学习/RL 进阶"),
    dict(title="Deep Learning（花书）", author="Ian Goodfellow, Yoshua Bengio, Aaron Courville", subject="人工智能",
         publisher="MIT Press", license="官方免费 HTML（作者网站放出）", status="external",
         source_url="https://www.deeplearningbook.org/",
         note="官网免费全文；深度学习理论根基，面试/读研理论深度必备"),
    dict(title="Interpretable Machine Learning（可解释机器学习）", author="Christoph Molnar", subject="人工智能",
         publisher="自出版", license="官方免费在线全书", status="external",
         source_url="https://christophm.github.io/interpretable-ml-book/",
         note="作者官网免费；模型可解释性方法全集，工程落地与答辩利器"),
    dict(title="Bayesian Methods for Hackers（贝叶斯方法 · 开源书）", author="Cam Davidson-Pilon",
         subject="人工智能", publisher="Addison-Wesley", license="官方免费在线全书", status="external",
         source_url="https://camdavidsonpilon.github.io/Probabilistic-Programming-and-Bayesian-Methods-for-Hackers/",
         note="官方免费；PyMC 概率编程实战，贝叶斯思维的代码视角"),
    dict(title="fastbook（fast.ai 深度学习实战）", author="Jeremy Howard, Sylvain Gugger", subject="人工智能",
         publisher="O'Reilly", license="官方免费 notebooks（github 放出）", status="external",
         source_url="https://github.com/fastai/fastbook",
         note="官方免费全部 notebook；top-down 学法，快速做出能跑的深度学习应用"),
    # ---- 编程基础 ----
    dict(title="Algorithms（算法 · Jeff Erickson）", author="Jeff Erickson", subject="编程基础",
         publisher="University of Illinois", license="官方免费 PDF（作者网站放出）", status="external",
         pdf_url="https://jeffe.cs.illinois.edu/teaching/algorithms/book/Algorithms-JeffE.pdf",
         source_url="https://jeffe.cs.illinois.edu/teaching/algorithms/book/",
         note="官方免费全书（约 23MB）；数据结构与算法基础，RM 电控/视觉代码功底"),
    dict(title="Beej's Guide to C Programming", author="Brian Beej Jorgensen Hall", subject="编程基础",
         publisher="beej.us", license="CC BY-NC-ND（作者官方免费）", status="external",
         pdf_url="https://beej.us/guide/bgc/pdf/bgc_usl_c_1.pdf",
         source_url="https://beej.us/guide/bgc/",
         note="作者官方免费（分上下两部分，本条为 Part 1，Part 2 在来源页）；STM32/电控 C 语言底子"),
    dict(title="Operating Systems: Three Easy Pieces", author="Remzi & Andrea Arpaci-Dusseau",
         subject="编程基础", publisher="Wisconsin大学", license="官方免费分章 PDF", status="external",
         source_url="https://pages.cs.wisc.edu/~remzi/OSTEP/",
         note="操作系统经典开放教材，官网免费分章下载；嵌入式底层理解"),
    dict(title="Pro Git（2e · 中文官方版）", author="Scott Chacon, Ben Straub", subject="编程基础",
         publisher="Apress", license="CC BY-NC-SA（官方免费）", status="external",
         source_url="https://git-scm.com/book/zh/v2",
         note="Git 官方文档出品的全书中文版，官网免费；工程协作基本功"),
    dict(title="The Missing Semester of Your CS Education（MIT）", author="MIT CSAIL", subject="编程基础",
         publisher="MIT", license="CC BY-NC-SA（官方免费）", status="external",
         source_url="https://missing.csail.mit.edu/",
         note="MIT 官方免费；Shell/工具链/调试/版本管理，大学课堂不教但天天用"),
    dict(title="SICP（计算机程序的构造和解释）", author="Harold Abelson, Gerald Sussman", subject="编程基础",
         publisher="MIT Press", license="CC BY-NC-SA（MIT 官方放出）", status="external",
         pdf_url="https://web.mit.edu/6.001/6.037/sicp.pdf",
         source_url="https://mitpress.mit.edu/9780262510870/",
         note="MIT 官方托管全书 PDF；编程思想经典，培养抽象能力"),
    dict(title="Automate the Boring Stuff with Python（Python 编程快速上手）", author="Al Sweigart",
         subject="编程基础", publisher="No Starch Press", license="CC BY-NC-SA（官方免费在线）", status="external",
         source_url="https://automatetheboringstuff.com/",
         note="作者官网免费全文；Python 自动化办公实操，零基础友好"),
    # ---- 考研公共课 ----
    dict(title="考研英语（一）历年真题解析", author="（红宝书 / 恋练有词配套）", subject="考研公共课",
         publisher="—", status="catalog",
         note="真题为核心；需自备正版文件导入"),
    dict(title="肖秀荣精讲精练 + 1000 题 / 肖四肖八", author="肖秀荣", subject="考研公共课",
         publisher="—", status="catalog",
         note="2028.07 起集中备考；需自备正版文件导入"),
    # ---- 示例大学·机械工程学院培养方案配套（按官网课程映射的 catalog 条目） ----
    *SEED_BOOKS_EXAMPLE,
]


def _deleted_presets() -> list:
    try:
        return json.loads(db.get_meta("library_deleted_presets") or "[]")
    except ValueError:
        return []


def seed() -> int:
    """幂等预置书目：按标题去重；用户主动删除过的预置书不再复活。"""
    deleted = _deleted_presets()
    n = 0
    for b in SEED_BOOKS:
        if b["title"] in deleted or db.find_book_by_title(b["title"]):
            continue
        db.add_book(**b)
        n += 1
    return n


def delete_book(bid: str) -> dict:
    """删除书目（含挂载文档/向量/文件）。预置书目记录删除标记，重启后不再重新预置。"""
    book = db.get_book(bid)
    db.delete_book(bid)
    if book and any(b["title"] == book["title"] for b in SEED_BOOKS):
        deleted = _deleted_presets()
        if book["title"] not in deleted:
            deleted.append(book["title"])
            db.set_meta("library_deleted_presets", json.dumps(deleted, ensure_ascii=False))
    return {"ok": True}


# ---------- 上传登记 ----------

def register_upload(title: str, ext: str, src_fileobj) -> str:
    """把上传的文件流写入书库（上传目录内受控路径）并登记为 local 书目。

    前端用文件夹选择器（webkitdirectory）批量选中文件逐个上传，
    服务端不接触任何用户提供的文件系统路径。
    同名上传一律新建条目而非静默丢弃——旧版本直接返回已有 id，导致
    用户上传修订版时以为替换成功，实际 RAG 一直用旧文件。重复条目可自行删除。
    """
    ext = ext.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("仅支持 PDF / TXT / Markdown / PPTX / 图片 / zip（老版 .ppt 请先另存为 .pptx）")
    f, dst = _new_book_file(ext)
    with f:
        shutil.copyfileobj(src_fileobj, f)
    return db.add_book(title=title, subject="我的教材", status="local", path=dst)


def register_zip(title: str, src_fileobj) -> list[dict]:
    """压缩包入库：展开其中每个受支持的文件，各自登记为一本 local 书目。

    zip 本身不留在书库；解出的成员文件落盘在上传目录内的临时子目录。
    """
    from . import rag as _rag  # noqa: F401  (保持与 attach 相同的依赖语义)
    f, zip_path = _new_book_file(".zip")
    with f:
        shutil.copyfileobj(src_fileobj, f)
    extract_dir = tempfile.mkdtemp(dir=_upload_root(), prefix="zip_")
    try:
        members = ingest.expand_zip(zip_path, extract_dir)
    except Exception:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
    out = []
    for name, path in members:
        btitle = os.path.splitext(name)[0][:100]
        # 同名成员也一律新建（不再静默跳过）；文件夹/压缩包批量导入的重复可自行删除
        bid = db.add_book(title=btitle, subject="我的教材", status="local", path=path,
                          note=f"来自压缩包「{title[:60]}」")
        out.append({"id": bid, "title": btitle, "status": "local"})
    return out


# ---------- 官方免费教材获取（带 SSRF 防护） ----------

def _safe_url(url: str) -> str:
    """仅允许 http/https 公网地址：拒绝 localhost、环回、私有与保留网段。"""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("仅允许 http/https 链接")
    host = p.hostname or ""
    if not host or host.lower() == "localhost" or host.endswith((".local", ".internal")):
        raise ValueError("禁止剪藏本机/本地地址")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise ValueError(f"域名解析失败: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_link_local
                or ip.is_multicast or ip.is_unspecified):
            # 校园网用户常想剪藏校内通知/内网文献站，要说明原因与替代路径，而不是一行生硬拒绝
            raise ValueError(
                f"出于安全考虑，剪藏仅支持公网链接（该地址解析到内网 {ip}）。"
                "校内页面可在浏览器另存为 PDF/TXT 后从「上传讲义」入库")
    return url


def _strip_default_port(url: str) -> str:
    """显式默认端口规范化（示例大学 WAF 对 https://…:443/ 返回 404），与 campus_net 同款。"""
    p = urllib.parse.urlsplit(url)
    try:
        port = p.port
    except ValueError:
        return url
    if port is None or (p.scheme, port) not in (("https", 443), ("http", 80)):
        return url
    netloc = p.hostname or ""
    if ":" in netloc:  # IPv6 字面量
        netloc = f"[{netloc}]"
    return p._replace(netloc=netloc).geturl()


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向逐跳复检 SSRF：公网直链可能 302 跳到内网/本机服务（对齐 campus_net）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe_url(_strip_default_port(newurl))
        return super().redirect_request(req, fp, code, msg, headers, _strip_default_port(newurl))


_opener = urllib.request.build_opener(_SafeRedirectHandler())


def fetch_pdf(bid: str) -> dict:
    """从官方直链下载开放教材全文到本地书库。"""
    book = db.get_book(bid)
    if not book:
        raise ValueError("书目不存在")
    if not book["pdf_url"]:
        raise ValueError("该书目没有官方直链，请从来源页手动下载后导入")
    url = _safe_url(_strip_default_port(book["pdf_url"]))
    f, dst = _new_book_file(".pdf")
    req = urllib.request.Request(url, headers={"User-Agent": "StudyPilot/0.1 (local study assistant)"})
    total = 0
    try:
        with _opener.open(req, timeout=60) as resp, f:
            while True:
                block = resp.read(256 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_BOOK_BYTES:
                    raise ValueError("文件超过 300MB 上限，已中止下载")
                f.write(block)
    except Exception as e:
        if os.path.exists(dst):
            os.remove(dst)
        # 已下载到本地的书目重试失败时保持 local 状态与文件记录，只记错误；
        # 不能把 path 清空（否则本地文件成孤儿、attach 直接不可用）
        cur = db.get_book(bid) or {}
        if cur.get("status") == "local" and cur.get("path"):
            db.update_book_file(bid, status="local", path=cur["path"],
                                error=f"重试下载失败: {str(e)[:200]}")
        else:
            db.update_book_file(bid, status="external", error=str(e)[:300])
        raise ValueError(f"下载失败（官方源可能需要代理）: {e}") from e
    if total < 1024:
        os.remove(dst)
        cur = db.get_book(bid) or {}
        if not (cur.get("status") == "local" and cur.get("path")):
            db.update_book_file(bid, status="external", error="下载内容过小，疑似非 PDF")
        raise ValueError("下载内容过小，疑似非 PDF")
    db.update_book_file(bid, status="local", path=dst, error="")
    return {"id": bid, "status": "local", "bytes": total}


# ---------- 网页剪藏入库（复用同一套 SSRF 防护） ----------

MAX_PAGE_BYTES = 5 * 1024 * 1024  # 单页上限 5MB


def _html_to_text(raw: bytes, charset: str) -> tuple[str, str]:
    """极简正文抽取：去 script/style、块级标签换行，返回 (title, text)。"""
    import html as html_mod
    from html.parser import HTMLParser

    class Extractor(HTMLParser):
        SKIP = {"script", "style", "noscript", "svg", "head"}
        BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                 "section", "article", "blockquote", "pre", "table", "ul", "ol"}

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.title = ""
            self._in_title = False
            self._skip_depth = 0
            self.parts: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag in self.SKIP:
                self._skip_depth += 1
            if tag == "title":
                self._in_title = True
            if tag in self.BLOCK:
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in self.SKIP and self._skip_depth:
                self._skip_depth -= 1
            if tag == "title":
                self._in_title = False
            if tag in self.BLOCK:
                self.parts.append("\n")

        def handle_data(self, data):
            if self._in_title:
                self.title += data
            elif not self._skip_depth:
                self.parts.append(data)

    parsed = Extractor()
    parsed.feed(raw.decode(charset, errors="replace"))
    title = html_mod.unescape(parsed.title).strip()[:120]
    lines = [ln.strip() for ln in "".join(parsed.parts).splitlines()]
    return title, "\n".join(ln for ln in lines if ln)


def import_url(url: str, title: str = "") -> dict:
    """抓取公开网页正文，存为 local 书目（可像教材一样挂载到空间参与 RAG）。"""
    url = _safe_url(_strip_default_port(url.strip()))
    req = urllib.request.Request(url, headers={"User-Agent": "StudyPilot/0.1 (local study assistant)"})
    try:
        with _opener.open(req, timeout=30) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(MAX_PAGE_BYTES + 1)
    except ValueError:
        raise  # _safe_url 的 SSRF 校验拒绝，保持原语义
    except Exception as e:
        # DNS 失败/超时/拒连等网络异常不是 ValueError，不接住会裸 500
        raise ValueError(f"网页抓取失败（检查网络或地址）：{str(e)[:200]}") from e
    if len(raw) > MAX_PAGE_BYTES:
        raise ValueError("网页超过 5MB 上限")
    if "pdf" in ctype or raw[:4] == b"%PDF":
        raise ValueError("该地址是 PDF，请使用「上传教材文件」或书目「获取 PDF」导入")
    if "html" not in ctype and "text/plain" not in ctype and ctype:
        raise ValueError(f"不支持的内容类型: {ctype}")
    charset = "utf-8"
    for part in ctype.split(";"):
        if part.strip().startswith("charset="):
            charset = part.split("=", 1)[1].strip(" \"'") or "utf-8"
    if charset.lower() not in ("utf-8", "utf8"):
        try:
            raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            charset = "gb18030"
    try:
        page_title, text = _html_to_text(raw, charset)
    except (LookupError, UnicodeDecodeError):
        page_title, text = _html_to_text(raw, "utf-8")
    if len(text.strip()) < 50:
        raise ValueError("未能抽取到有效正文（页面可能是纯脚本渲染）")
    name = (title or page_title or urllib.parse.urlparse(url).netloc).strip()[:100]
    # 按 URL 判重（同标题不同页是两篇内容；同 URL 换标题重复剪藏才是真重复）
    if db.find_book_by_url(url):
        raise ValueError(f"该网页已在书库（URL 相同）：《{name}》")
    f, dst = _new_book_file(".txt")
    with f:
        f.write(f"来源: {url}\n\n{text}".encode("utf-8"))
    bid = db.add_book(title=f"网页：{name}", subject="我的教材", status="local", path=dst,
                      source_url=url, note="网页剪藏")
    return {"id": bid, "title": f"网页：{name}", "chars": len(text)}


# ---------- 挂载到课程空间 ----------

def attach(bid: str, space_id: str) -> dict:
    """把一本 local 书目挂载进课程空间：建立文档并走 RAG 索引管线。幂等。

    书库文件只可能由 _new_book_file 经 mkstemp 生成于上传目录内；
    挂载前再做一次 realpath 前缀校验，非法路径直接拒绝。
    """
    book = db.get_book(bid)
    if not book:
        raise ValueError("书目不存在")
    if not db.get_space(space_id):
        raise ValueError("课程空间不存在")
    existing = db.get_book_document(bid, space_id)
    if existing and db.get_document(existing):
        doc = db.get_document(existing)
        return {"document_id": existing, "status": "already", "chunks": doc["chunks"]}
    if book["status"] != "local" or not book["path"]:
        raise ValueError("该书目还没有本地文件，请先获取或上传导入")
    real = os.path.realpath(book["path"])
    if not real.startswith(_upload_root() + os.sep):
        raise ValueError("书库文件路径异常")
    if not os.path.exists(real):
        raise ValueError("书目文件已丢失，请重新获取或上传导入")
    ext = os.path.splitext(real)[1]
    did = db.add_document(space_id, book["title"] + ext, real, doc_id=db.new_id())
    try:
        n = rag.index_document(space_id, did)
    except Exception as e:
        # 只回滚文档记录，不删文件（该路径是书库文件本身，可能被多个空间的挂载共享）
        db.delete_document(did, remove_file=False)
        raise ValueError(f"索引失败: {e}") from e
    db.add_book_document(bid, space_id, did)
    return {"document_id": did, "status": "ready", "chunks": n}


def _upload_root() -> str:
    root = os.path.realpath(settings.upload_dir)
    os.makedirs(root, exist_ok=True)
    return root


def _new_book_file(ext: str):
    """在上传目录内经 mkstemp 创建受控新文件，返回 (二进制文件对象, realpath)。

    写入一律走 mkstemp 返回的文件描述符（os.fdopen），不按路径打开，
    目录逃逸/TOCTOU 面为零；路径仅用于落库与后续受控读取。
    """
    root = _upload_root()
    fd, dst = tempfile.mkstemp(dir=root, suffix=ext)
    f = os.fdopen(fd, "wb")
    real = os.path.realpath(dst)
    if not real.startswith(root + os.sep):
        f.close()
        os.remove(dst)
        raise ValueError("书库文件路径异常")
    return f, real
