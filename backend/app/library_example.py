"""示例大学·机械工程学院培养方案配套书目（catalog 条目，仅书目元数据）。

数据来源（官网公开 PDF，2023-11 挂网，抓取于 2026-09）：
- 《机械设计制造及其自动化/材料成型及控制工程/工业设计/农业机械化及其自动化
  专业培养方案（2021版，执行年限 2022-2027）》
  http://mech.example.edu.cn/2023/1101/c23679a199538/page.htm
  PDF: http://mech.example.edu.cn/_upload/article/files/9b/8e/095452dc440e8e82d27b8fadbe86/9f30aa88-1990-4be6-92c3-6e822b302a0f.pdf

版权边界与真实性的边界：
- 培养方案只列课程不列教材（每门课的指定教材在校内课程教学大纲/教务系统中）。
  本表按课程逐门映射到国内主流教材；note 均注明「对应示例大学课程+学期」，
  示例大学实际采用的版次/作者以课程大纲为准，连上校园网后可在教务系统核实。
- 全部为 status=catalog：只收书目信息，不含任何全文内容；
  正版全文需用户自行获得后经「上传」进入书库。
"""

SEED_BOOKS_EXAMPLE = [
    # ---- 通识·思政（培养方案「思想政治类」16 学分） ----
    dict(title="思想道德与法治（2023年版）", author="本书编写组", subject="通识思政",
         publisher="高等教育出版社", status="catalog",
         note="示例大学大一秋冬《思想道德修养与法律基础》课程教材；思政教材请以教务指定最新修订版为准"),
    dict(title="中国近现代史纲要（2023年版）", author="本书编写组", subject="通识思政",
         publisher="高等教育出版社", status="catalog",
         note="示例大学大一春夏课程教材；同上以最新修订版为准"),
    dict(title="马克思主义基本原理（2023年版）", author="本书编写组", subject="通识思政",
         publisher="高等教育出版社", status="catalog",
         note="示例大学大一春夏课程教材；同上以最新修订版为准"),
    dict(title="毛泽东思想和中国特色社会主义理论体系概论（2023年版）", author="本书编写组",
         subject="通识思政", publisher="高等教育出版社", status="catalog",
         note="示例大学大二「毛概（1）（2）」课程教材；2023 年版已并入习思想概论内容，以教务指定为准"),
    dict(title="习近平新时代中国特色社会主义思想概论（2023年版）", author="本书编写组",
         subject="通识思政", publisher="高等教育出版社", status="catalog",
         note="思政系列配套；与毛概课程配合使用，以教务指定为准"),
    dict(title="某省省情教程", author="某省省教育厅组编", subject="通识思政",
         publisher="某省省教育厅组编", status="catalog",
         note="示例大学特色必修课《某省省情》（大一秋冬）教材；版次待教务系统核实"),
    # ---- 通识·外语与计算机（大一全年） ----
    dict(title="Python语言程序设计基础（第2版）", author="嵩天、礼欣、黄天羽", subject="编程基础",
         publisher="高等教育出版社", status="catalog",
         note="示例大学计算机类公共课《Python 程序设计》（大一全年，可替代《大学计算机》）主流教材；示例大学实际采用待核实"),
    # ---- 数学（高数/线代/概率已另有预置，此处补工程数学缺口） ----
    dict(title="复变函数与积分变换（第三版）", author="华中科技大学数学系", subject="数学基础",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《工程数学1》（大二秋冬，5 学分）的复变/积分变换部分主流教材；线代与概率部分见同济线代、浙大概率"),
    # ---- 物理·力学（学科大类必修+选修） ----
    dict(title="物理学（第六版）上/下册", author="马文蔚、解希顺、周雨青", subject="物理·力学",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《大学物理1-1/1-2》（大一～大二）主流教材，工科机类通用；版次以课程大纲为准"),
    dict(title="理论力学（I）（第8版）", author="哈工大理论力学教研室编、王铎主编", subject="物理·力学",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《理论力学（中）》（大二秋冬，4 学分）主流教材；机类考研力学基础"),
    dict(title="材料力学（第6版）Ⅰ/Ⅱ", author="刘鸿文", subject="物理·力学",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《材料力学（中）》（大二春夏，4 学分）主流教材；与书库另收的范钦珊版互补"),
    dict(title="流体力学", author="张也影", subject="物理·力学",
         publisher="高等教育出版社", status="catalog",
         note="示例大学三秋冬选修《流体力学》（2 学分）可用水力学/流体力学入门教材之一；待核实"),
    dict(title="弹性力学（第5版）", author="徐芝纶", subject="物理·力学",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《弹性力学基础》（二/三学期选修，2.5 学分）经典教材；有限元先修"),
    dict(title="热工基础与应用（第3版）", author="傅秦生", subject="物理·力学",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《热工学》（大三秋冬选修，2 学分）对应热工基础类教材；待核实"),
    dict(title="空气动力学", author="钱翼稷", subject="物理·力学",
         publisher="北京航空航天大学出版社", status="catalog",
         note="示例大学《空气动力学基础》（大三秋冬选修）可选用教材；待核实"),
    # ---- 机械设计主线（机类1/2 + 专业核心） ----
    dict(title="机械制图（第7版）", author="何铭新、钱可强、徐祖茂", subject="机械设计",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《机械制图（机类1/2）》（大一秋冬+春夏，3.5+4 学分）主流教材；先进成图大赛底子"),
    dict(title="机械原理（第九版）", author="孙桓、陈作模、葛文杰", subject="机械设计",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《机械原理》（大二春夏，3.5 学分）主流教材；与书库另收的申永胜《机械原理教程》互补"),
    dict(title="机械设计（第十版）", author="濮良贵、陈国定、吴立言", subject="机械设计",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《机械设计》（大三秋冬，3.5 学分）主流教材；与吴宗泽版互补，考研机械设计基础轮"),
    dict(title="几何量公差与检测（第11版）", author="甘永立", subject="机械设计",
         publisher="上海科学技术出版社", status="catalog",
         note="示例大学《互换性与测量技术》（大三秋冬，2 学分）主流参考；公差配合查表实操"),
    dict(title="机械优化设计", author="孙靖民", subject="机械设计",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《机械优化设计》（大三选修，2 学分）常用教材；待核实"),
    dict(title="机械动力学", author="张策", subject="机械设计",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《机械系统动力学》（大三选修，2 学分）可用教材；振动/动力学进阶；待核实"),
    # ---- 控制与机电（专业核心+机电模块） ----
    dict(title="机械工程控制基础（第7版）", author="杨叔子、杨克冲等", subject="控制与机电",
         publisher="华中科技大学出版社", status="catalog",
         note="示例大学《机械工程控制基础》（大三秋冬，2.5 学分）主流教材；自控入门，822 考研先修"),
    dict(title="机械工程测试技术基础（第4版）", author="熊诗波、黄长艺", subject="控制与机电",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《测试技术》（大三春夏，2.5 学分）主流教材；传感器+信号分析基础"),
    dict(title="液压与气压传动（第4版）", author="章宏甲、黄谊主编", subject="控制与机电",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《液气压传动与控制》对应教材——该课为示例大学国家级精品资源共享课程，工程机械/农机方向核心"),
    dict(title="单片机原理及接口技术（C51编程）（第3版）", author="张毅刚", subject="控制与机电",
         publisher="人民邮电出版社", status="catalog",
         note="示例大学《单片机原理及应用》（机电/农机模块选修，3 学分）主流教材；STM32 之前先吃透 51"),
    dict(title="PLC编程及应用（S7-1200）", author="廖常初", subject="控制与机电",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《可编程控制器原理及应用》（多模块选修）对应 PLC 教材；机型以实验室实际为准（西门子/三菱）"),
    dict(title="电机与拖动", author="唐介", subject="控制与机电",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《电机与控制》（机电模块，2.5 学分）可用教材；机电传动的电机侧基础；待核实"),
    dict(title="电力电子技术（第5版）", author="王兆安、刘进军", subject="控制与机电",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《变流技术与交流调速》（机电模块选修）对应电力电子主流教材；伺服驱动底层"),
    dict(title="传感器（第5版）", author="唐文彦", subject="控制与机电",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《传感器原理及应用》（双语/机电模块）主流教材；测试技术后续"),
    # ---- 制造与智能制造 ----
    dict(title="机械制造技术基础（第4版）", author="卢秉恒", subject="机器人·智能制造",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《机械制造技术基础（双语）》（大三秋冬，2.5 学分）主流教材；工艺/夹具/质量主线"),
    dict(title="有限元分析基础教程", author="曾攀", subject="机器人·智能制造",
         publisher="清华大学出版社", status="catalog",
         note="示例大学《有限元分析》（大三春夏选修，2 学分）可用教材；ANSYS/CAE 理论底子"),
    dict(title="数据库系统概论（第6版）", author="王珊、杜小勇、陈红", subject="机器人·智能制造",
         publisher="高等教育出版社", status="catalog",
         note="示例大学《数据库技术及应用》（智能制造模块选修，2 学分）主流教材；工业数据底子"),
    # ---- 车辆工程模块 ----
    dict(title="汽车理论（第6版）", author="余志生", subject="车辆工程",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《汽车理论（双语）》（大三春夏选修）主流教材；动力性/经济性/操稳经典"),
    dict(title="汽车构造（第3版）上/下册", author="陈家瑞", subject="车辆工程",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《汽车构造（双语）》（大三秋冬选修）主流教材；整车结构权威入门"),
    dict(title="汽车设计（第5版）", author="王望予", subject="车辆工程",
         publisher="机械工业出版社", status="catalog",
         note="示例大学《汽车设计》（车辆模块）常用教材；待核实"),
    # ---- 材料成型及控制工程专业（同院第二专业核心课） ----
    dict(title="金属学与热处理（第2版）", author="崔忠圻、覃耀春", subject="材料成型",
         publisher="机械工业出版社", status="catalog",
         note="示例大学材料成型专业《金属学与热处理》（大二春夏，3 学分）经典教材；热处理工艺权威"),
]
