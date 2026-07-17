#!/usr/bin/env python3
"""Build a non-destructive 102-case HemaGuide similarity test dataset."""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from generate_similarity_case_set import LEUKEMIA, LYMPHOMA, make_doc, spec


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "test_data" / "case_similarity_50"
OUTPUT_ROOT = PROJECT_ROOT / "test_data" / "case_similarity_102"

S = spec

NEW_LEUKEMIA = [
    S("LEU-026", "KMT2A重排AML", "初诊、高白细胞", 44, "女", 1, "KMT2A::MLLT3，RAS通路突变", "无", "白细胞96×10^9/L，齿龈浸润，已完成白细胞减灭。", "请制定诱导、MRD及移植方案。", "采用强化诱导，以融合基因监测MRD，缓解后尽早评估异基因移植。"),
    S("LEU-027", "MECOM重排AML", "初诊、不良风险", 50, "男", 1, "inv(3)/MECOM，单7", "无", "伴明显血小板增多和进行性贫血，配型已启动。", "是否应直接规划首次缓解期移植？", "按不良风险AML诱导，同步完成供者搜索，获得缓解后进入移植。"),
    S("LEU-028", "NUP98::NSD1阳性AML", "儿童初诊、FLT3阳性", 12, "女", 1, "NUP98::NSD1，FLT3-ITD，WT1高表达", "无", "诱导前高白细胞，无中枢神经系统受累。", "如何整合FLT3抑制剂和儿童移植路径？", "采用儿童AML强化方案并整合FLT3导向治疗，依据MRD评估移植。"),
    S("LEU-029", "AML伴骨髓增生异常相关基因突变", "初诊、继发性", 70, "男", 2, "SRSF2、BCOR和STAG2突变", "既往未明确诊断的长期大细胞性贫血", "骨髓原始细胞27%，合并心功能不全。", "低强度联合方案是否更合适？", "综合体能和心功能选择去甲基化药联合BCL2抑制剂，动态评估耐受性。"),
    S("LEU-030", "NPM1突变AML", "异基因移植后血液学复发", 48, "女", 1, "NPM1突变，FLT3野生型，供者嵌合率71%", "7+3；HiDAC；异基因移植", "移植后16个月复发，无活动性GVHD。", "挽救、减停免疫抑制和DLI如何排序？", "使用挽救治疗降低疾病负荷，并根据GVHD风险调整免疫抑制及评估DLI。"),
    S("LEU-031", "NPM1突变AML", "化疗后分子复发", 57, "男", 0, "NPM1 MRD连续两次上升，形态学缓解", "7+3；3个疗程HiDAC", "血象正常，NPM1/ABL1比值3个月内上升近10倍。", "是否在形态学复发前启动治疗？", "复核分子复发后早期干预，同步进行移植评估，避免等待形态学进展。"),
    S("LEU-032", "IDH2突变AML", "低强度治疗后进展", 74, "女", 2, "IDH2 R140Q，RUNX1突变", "azacitidine联合venetoclax 9个疗程", "骨髓原始细胞回升至18%，伴持续粒细胞减少。", "是否转入IDH2靶向治疗？", "考虑IDH2靶向挽救，同时处理感染风险并评估临床试验。"),
    S("LEU-033", "FLT3-TKD阳性AML", "FLT3抑制剂后难治", 60, "男", 1, "FLT3 D835，WT1突变", "强化化疗；gilteritinib", "靶向治疗6个月后原始细胞再度增多。", "如何处理FLT3通路耐药？", "复查克隆演化并优先临床试验或非交叉联合挽救，缓解后评估移植。"),
    S("LEU-034", "AML", "骨髓缓解期孤立中枢复发", 40, "女", 1, "NPM1野生型，脑脊液流式阳性", "7+3；HiDAC巩固", "出现头痛和复视，骨髓检查仍缓解。", "局部与全身挽救如何组合？", "采用鞘内治疗与具中枢渗透性的全身治疗，缓解后评估移植。"),
    S("LEU-035", "AML", "姊娠中期初诊", 32, "女", 1, "CEBPA bZIP区单突变，FLT3阴性", "无", "姊娘22周，骨髓原始细胞52%，无严重器官功能障碍。", "如何平衡诱导时机与胎儿风险？", "由血液、产科和新生儿多学科决策，在妊娠中期尽快启动必要的AML治疗。"),
    S("LEU-036", "AML", "初诊合并侵袭性真菌感染", 67, "男", 3, "DNMT3A、TET2突变，中间风险核型", "无", "肺部疑似侵袭性曲霉感染，需氧支持。", "应先控制感染还是立即诱导？", "先快速稳定感染和器官功能，根据AML进展速度选择短暂延迟或低强度起始。"),
    S("LEU-037", "Ph样B-ALL", "初诊、诱导后MRD阳性", 19, "男", 0, "CRLF2重排，JAK2 R683G，MRD 1.2%", "儿童样ALL诱导", "形态学缓解但MRD下降不足。", "是否整合JAK抑制和免疫治疗？", "进行免疫导向的MRD清除并评估研究性JAK通路治疗，同步规划移植。"),
    S("LEU-038", "Ph阴性B-ALL", "blinatumomab后MRD持续", 36, "女", 0, "CD19阳性，IKZF1缺失，MRD 0.03%", "多药化疗；blinatumomab 2个疗程", "仍处形态学缓解，已找到匹配供者。", "是否需再清除MRD后移植？", "复核MRD标本并考虑更换免疫靶点，在可控的疾病负荷下进入移植。"),
    S("LEU-039", "复发B-ALL", "inotuzumab后缓解、待移植", 54, "男", 1, "CD22阳性，MRD阴性", "强化化疗；inotuzumab 2个疗程", "既往轻度脂肪肝，胆红素正常，准备异基因移植。", "如何降低肝静脉闭塞病风险？", "限制额外肝毒性暴露，优化预处理强度并在移植期严密监测肝静脉闭塞病。"),
    S("LEU-040", "T-ALL", "首次骨髓复发", 25, "男", 1, "CD7强阳性，NOTCH1突变", "儿童样ALL方案完成维持", "停药8个月后复发，脑脊液阴性。", "nelarabine挽救后是否直接移植？", "采用含nelarabine的T系挽救，达MRD低水平后尽快进入异基因移植。"),
    S("LEU-041", "ETP-ALL", "异基因移植后复发", 30, "女", 2, "ETP免疫表型，FLT3突变", "多药化疗；异基因移植", "移植后7个月复发，伴轻度慢性GVHD。", "移植后早期复发如何安排挽救？", "优先临床试验或T系挽救，平衡GVHD后评估减停免疫抑制及细胞治疗。"),
    S("LEU-042", "BCR::ABL1阳性混合表型急性白血病", "老年初诊", 69, "男", 2, "B/髓系MPAL，BCR::ABL1 p210", "无", "合并冠心病和糖尿病，无中枢受累。", "低强度ALL导向治疗如何联合TKI？", "采用TKI联合年龄适配的ALL导向治疗，按BCR::ABL1与流式MRD调整方案。"),
    S("LEU-043", "慢性髓性白血病", "无治疗缓解尝试后分子复发", 46, "女", 0, "BCR::ABL1回升至0.18% IS，无耐药突变", "dasatinib深度分子缓解5年后停药", "停药7个月失去MMR，无症状。", "是否应恢复原TKI？", "立即恢复有效TKI并密集监测BCR::ABL1，多数患者可再次获得MMR。"),
    S("LEU-044", "慢性髓性白血病", "淋系急变、多TKI耐药", 58, "男", 2, "BCR::ABL1 T315I，CD19阳性", "多种TKI；ponatinib", "骨髓淋系原始细胞43%，无合适同胞供者。", "免疫治疗、TKI与移植如何组合？", "采用对T315I有活性的TKI联合B系导向挽救，获得第二慢性期后进入移植。"),
    S("LEU-045", "MDS伴原始细胞增多", "高危、移植候选", 62, "女", 1, "U2AF1、RUNX1和ASXL1突变，原始细胞12%", "无", "输血依赖，已找到匹配非血缘供者。", "移植前是否需去甲基化减瘤？", "根据等待时间和疾病动力学选择桥接治疗，避免不必要延误移植。"),
    S("LEU-046", "低危MDS伴del(5q)", "lenalidomide后失应答", 73, "女", 1, "del(5q)，新出现TP53低负荷克隆", "lenalidomide 30个月", "再次输血依赖，骨髓原始细胞4%。", "失应答后应如何调整治疗？", "复核克隆演化和风险分层，根据症状与进展风险选择ESA、去甲基化或试验。"),
    S("LEU-047", "慢性髓单核细胞白血病", "去甲基化后部分缓解、待移植", 59, "男", 1, "ASXL1、TET2、CBL突变", "decitabine 6个疗程", "白细胞和脾大改善，仍有输血需求。", "部分缓解是否足以进入移植？", "若疾病负荷稳定且体能允许，不必追求完全缓解而延误移植。"),
    S("LEU-048", "MDS/MPN伴中性粒细胞增多", "进展性、青年", 39, "女", 1, "SETBP1、ETNK1和ASXL1突变，BCR::ABL1阴性", "hydroxyurea", "白细胞进行性增高并伴脾大，原始细胞8%。", "是否应进入异基因移植？", "在专家病理复核后进行疾病控制，鉴于年轻和进展性尽早评估移植。"),
    S("LEU-049", "BCR::ABL1阴性骨髓增殖性肿瘤", "转化为AML", 65, "男", 2, "JAK2 V617F，TP53和NRAS突变", "ruxolitinib治疗骨髓纤维化3年", "骨髓原始细胞32%，脾大明显，血小板减少。", "转化后如何争取移植机会？", "采用适合体能的AML挽救降低疾病负荷，缓解后尽快进行移植。"),
    S("LEU-050", "母细胞性浆细胞样树突细胞肿瘤", "初诊、皮肤与骨髓受累", 43, "男", 0, "CD123强阳性，TCF4阳性", "无", "多发紫红色皮损，骨髓受累28%，脑脊液阴性。", "CD123导向治疗后是否移植？", "采用CD123导向诱导并纳入中枢评估和预防，首次缓解期评估移植。"),
    S("LEU-051", "慢性淋巴细胞白血病", "BTK和BCL2抑制剂后进展", 68, "女", 1, "del(17p)，TP53突变，BTK C481S", "ibrutinib；venetoclax联合抗CD20抗体", "淋巴结和淋巴细胞逐渐增多，PET无明显转化特征。", "双通路耐药后如何选择后续治疗？", "重新排除Richter转化，优先非共价BTK抑制剂、细胞治疗或临床试验。"),
]

NEW_LYMPHOMA = [
    S("LYM-026", "原发睪丸弥漫性大B细胞淋巴瘤", "初诊、局限期", 66, "男", 1, "MYD88 L265P，CD20阳性", "无", "单侧睪丸肿大，未发现中枢或对侧睪丸受累。", "如何安排全身治疗、中枢预防和对侧放疗？", "采用抗CD20免疫化疗，整合中枢预防及对侧睪丸放疗。"),
    S("LYM-027", "血管内大B细胞淋巴瘤", "初诊、多器官受累", 72, "女", 3, "CD20阳性，MYD88 L265P", "无", "发热、低氧、高LDH和血细胞减少，皮肤随机活检确诊。", "危重状态下如何启动治疗？", "快速完成必要分期后启动减量预阶段及抗CD20免疫化疗，严密支持多器官功能。"),
    S("LYM-028", "原发皮肤弥漫性大B细胞淋巴瘤，腿型", "局部复发", 79, "女", 1, "BCL2和MUM1阳性，MYD88突变", "局部放疗后缓解18个月", "同侧下肢出现多个新结节，无内脏受累。", "再放疗与全身治疗如何选择？", "根据病灶范围与既往剂量选择局部控制或抗CD20为基础的全身治疗。"),
    S("LYM-029", "EBV阳性弥漫性大B细胞淋巴瘤", "老年初诊", 81, "男", 2, "EBER弥漫阳性，CD20阳性，PD-L1高表达", "无", "多站淋巴结和肺受累，合并慢性心功能不全。", "如何在治疗强度与心脏毒性之间平衡？", "采用老年体能适配的抗CD20方案，根据心功能调整蒽环类暴露。"),
    S("LYM-030", "滤泡性淋巴瘤转化为DLBCL", "首次组织学转化", 61, "女", 1, "MYC野生型，BCL2重排，CD20阳性", "观察等待4年；局部放疗", "出现快速增大的腹膜后包块和B症状，活检确认转化。", "应按初治DLBCL还是复发滤泡性淋巴瘤治疗？", "按转化性大B细胞淋巴瘤采用治愈意图的免疫化疗，根据疗效评估巩固。"),
    S("LYM-031", "弥漫性大B细胞淋巴瘤", "双特异性抗体后进展", 57, "男", 2, "CD19阴性，CD20弱阳性，CD22阳性", "R-CHOP；自体移植；CAR-T；CD20×CD3双抗", "多线治疗后骨髓和骨骼进展，伴细胞减少。", "抗原丢失后还有哪些系统治疗方向？", "复核抗原表达和骨髓储备，优先CD22导向治疗、新型细胞治疗或临床试验。"),
    S("LYM-032", "弥漫性大B细胞淋巴瘤", "自体移植后晚期孤立骨复发", 48, "女", 0, "CD20阳性，GCB型", "R-CHOP；挽救化疗；自体移植", "移植后5年出现单一股骨病灶，活检确认复发。", "局部放疗是否足够？", "完成全身分期后采用局部控制并评估全身挽救，避免将隐匿播散误判为局限病变。"),
    S("LYM-033", "原发中枢神经系统淋巴瘤", "自体移植后复发", 59, "男", 1, "MYD88 L265P，CD20阳性", "高剂量甲氨蝶呤为基础的联合方案；塞替派自体移植", "移植后20个月出现新的深部脑实质病灶。", "复发后如何选择BTK抑制、免疫治疗或再挑战？", "根据既往甲氨蝶呤敏感性、器官功能和可及性选择中枢有活性的挽救方案。"),
    S("LYM-034", "原发玻璃体视网膜淋巴瘤", "双眼受累、无脑实质病灶", 63, "女", 0, "玻璃体IL-10升高，MYD88 L265P", "无", "视力波动和飞蚊症，脑MRI及脑脊液阴性。", "局部眼内治疗与全身中枢治疗如何取舍？", "由眼科与中枢淋巴瘤团队共同评估，采用眼内控制并根据双眼疾病评估全身治疗。"),
    S("LYM-035", "滤泡性淋巴瘤", "多线复发、EZH2突变", 65, "男", 1, "EZH2 Y646N，CD20阳性", "免疫化疗；lenalidomide联合抗CD20抗体", "第三次进展，肿瘤负荷中等，无转化证据。", "EZH2抑制、双抗和CAR-T如何排序？", "根据病程速度、治疗目标和可及性选择EZH2抑制或免疫治疗，预留细胞治疗。"),
    S("LYM-036", "滤泡性淋巴瘤", "怀疑转化、待再活检", 54, "女", 1, "t(14;18)，新出现LDH升高", "抗CD20单药后缓解3年", "单一腹股沟淋巴结迅速增大，PET SUVmax 24。", "活检部位和治疗时机如何确定？", "优先对代谢最高且可安全取样的病灶活检，在病理明确前避免盲目按惰性淋巴瘤治疗。"),
    S("LYM-037", "白血病样非淋巴结性套细胞淋巴瘤", "无症状、低增殖", 62, "男", 0, "SOX11阴性，t(11;14)，ki-67 5%", "无", "外周血和骨髓受累，淋巴结不大，血象稳定。", "是否可以观察等待？", "在无症状、无器官威胁且指标稳定时观察，按预设间隔监测。"),
    S("LYM-038", "套细胞淋巴瘤", "CAR-T后CD19阴性复发", 60, "女", 2, "CD19阴性，CD20阳性，TP53突变", "免疫化疗；BTK抑制剂；CD19 CAR-T", "CAR-T后6个月高增殖性复发，伴血小板减少。", "抗原逃逸后如何快速挽救？", "根据CD20表达与骨髓储备考虑双特异性抗体或新型靶向试验，同时控制高肿瘤负荷。"),
    S("LYM-039", "华氏巨球蛋白血症/淋巴浆细胞淋巴瘤", "BTK抑制剂不耐受", 71, "男", 1, "MYD88 L265P，CXCR4野生型", "zanubrutinib后反复房颤", "IgM逐渐升高，伴轻度贫血，无高黏滞症状。", "如何在心脏风险下更换治疗？", "处理可逆性心脏因素，选择非BTK依赖方案或不同安全性特征的靶向治疗。"),
    S("LYM-040", "结内边缘区淋巴瘤", "初诊、高肿瘤负荷", 64, "女", 1, "KLF2突变，CD20阳性", "无", "多站淋巴结、脾大和输血依赖性贫血。", "一线是否应使用抗CD20联合治疗？", "已有治疗指征，采用抗CD20为基础的全身治疗，按并存症调整强度。"),
    S("LYM-041", "边缘区淋巴瘤转化为DLBCL", "首次转化", 69, "男", 2, "TP53突变，MYC蛋白高表达", "抗CD20单药；bendamustine联合抗CD20抗体", "出现B症状和骨外快速进展，活检证实转化。", "老年高危转化如何平衡强度？", "按侵袭性大B细胞淋巴瘤治疗，通过预阶段和支持治疗降低早期毒性。"),
    S("LYM-042", "小淋巴细胞淋巴瘤", "怀疑Richter转化", 67, "女", 2, "TP53突变，某淋巴结SUVmax 19", "acalabrutinib治疗2年", "出现发热、LDH升高和单个淋巴结迅速增大。", "如何选择活检部位并避免延误？", "对PET代谢最高的可及病灶尽快切除或粗针活检，病理确认后再选择转化治疗。"),
    S("LYM-043", "经典型霍奇金淋巴瘤", "PD-1抑制后缓解、待异基因移植", 33, "男", 0, "PD-L1高表达，CD30阳性", "ABVD；挽救化疗；自体移植；nivolumab", "PD-1抑制后完全代谢缓解，有匹配供者。", "移植时机和GVHD风险如何管理？", "在缓解期完成移植评估，结合PD-1暴露间隔与GVHD预防策略降低免疫毒性。"),
    S("LYM-044", "经典型霍奇金淋巴瘤", "妊娠早期初诊", 29, "女", 0, "CD30阳性，EBER阴性", "无", "妊娑1周，颈纵隔病灶，无B症状或器官威胁。", "能否观察至妊娠中期再治疗？", "由血液和产科团队分期，在无器官威胁时密切观察，妊娠中期再根据进展启动治疗。"),
    S("LYM-045", "结节性淋巴细胞为主型B细胞淋巴瘤", "转化为大B细胞淋巴瘤", 45, "男", 0, "LP细胞CD20阳性，CD30阴性", "局部放疗后缓解6年", "腹膜后病灶快速增大，活检显示大B细胞转化。", "转化后应如何进行免疫化疗？", "按转化性大B细胞淋巴瘤采用抗CD20免疫化疗，根据PET反应规划巩固。"),
    S("LYM-046", "滤泡辅助T细胞表型的结内外周T细胞淋巴瘤", "初诊、高危", 58, "女", 1, "RHOA G17V，TET2和IDH2 R172突变", "无", "广泛淋巴结、皮疹和高丙种球蛋白血症。", "一线治疗和首次缓解巩固如何选择？", "采用T细胞淋巴瘤导向诱导，并在缓解后根据风险与体能评估移植巩固。"),
    S("LYM-047", "ALK阴性间变性大细胞淋巴瘤", "初诊、DUSP22重排", 52, "男", 1, "CD30强阳性，DUSP22重排，TP63阴性", "无", "多站淋巴结受累，无骨髓受累。", "DUSP22状态是否改变一线强度和移植决策？", "采用CD30导向联合方案，预后标志作为整体风险的一部分而非单独决定巩固。"),
    S("LYM-048", "肝脾T细胞淋巴瘤", "初诊、年轻高危", 28, "男", 2, "TCRγδ克隆，i(7q)，STAT5B突变", "无", "巨脾、全血细胞减少和高热，淋巴结不大。", "如何快速获得缓解并衔接移植？", "采用非CHOP为主的强化挽救思路，诱导同期完成供者搜索并尽快移植。"),
    S("LYM-049", "成人T细胞白血病/淋巴瘤", "急性型、高钙血症", 55, "女", 2, "HTLV-1阳性，CCR4高表达", "无", "广泛淋巴结、皮损及高钙血症，伴机会性感染风险。", "如何同时控制高钙、肿瘤和感染风险？", "立即处理高钙并启动ATL导向治疗，同时加强机会性感染预防并评估移植。"),
    S("LYM-050", "蕲样肉芽肿/Sézary综合征", "皮肤红皮病期、多线治疗", 70, "男", 1, "CCR4阳性，外周血Sézary细胞克隆", "光疗；bexarotene；体外光化学疗法", "全身瘙痒、红皮病和血液受累，无大细胞转化。", "下一步全身治疗如何选择？", "根据血液负荷、CCR4表达和感染风险选择靶向免疫治疗，并继续皮肤支持。"),
    S("LYM-051", "原发皮肤γδT细胞淋巴瘤", "初诊、皮下与骨髓受累", 41, "女", 1, "TCRγδ克隆，CD56阳性，EBER阴性", "无", "多发疼痛性皮下结节、发热及血细胞减少。", "是否需强化诱导并在缓解期移植？", "在专家病理复核后采用侵袭性T细胞淋巴瘤方案，获得缓解后评估移植。"),
]


def case_text(item: dict) -> str:
    return " ".join(str(item[key]) for key in ("diagnosis", "phase", "biomarkers", "prior", "course", "question", "decision"))


def normalized(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text).lower()


def shingles(text: str, width: int = 3) -> set[str]:
    value = normalized(text)
    return {value[index:index + width] for index in range(max(0, len(value) - width + 1))}


def similarity(left: dict, right: dict) -> float:
    a, b = shingles(case_text(left)), shingles(case_text(right))
    return len(a & b) / len(a | b) if a or b else 1.0


def manifest_row(group: str, item: dict, path: Path, version: str) -> dict:
    return {
        "case_id": item["code"], "group": group, "role": item["role"],
        "dataset_version": version, "diagnosis": item["diagnosis"],
        "phase": item["phase"], "age": item["age"], "sex": item["sex"],
        "ECOG": item["ecog"], "biomarkers": item["biomarkers"],
        "relative_path": str(path.relative_to(OUTPUT_ROOT)),
    }


def main() -> None:
    if not SOURCE_ROOT.exists():
        raise SystemExit(f"Source dataset missing: {SOURCE_ROOT}")
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    all_groups = {
        "leukemia": (LEUKEMIA, NEW_LEUKEMIA),
        "lymphoma": (LYMPHOMA, NEW_LYMPHOMA),
    }
    manifest_rows, diversity_rows = [], []

    for group, (existing, additions) in all_groups.items():
        assert len(existing) == 25 and len(additions) == 26
        assert [item["code"] for item in additions] == [
            f"{'LEU' if group == 'leukemia' else 'LYM'}-{number:03d}" for number in range(26, 52)
        ]
        items = existing + additions
        history = [item for item in items if item["role"] == "history"]
        assert len(history) == 50 and sum(item["role"] == "query" for item in items) == 1

        signatures = {
            normalized("|".join(str(item[key]) for key in ("diagnosis", "phase", "biomarkers", "prior")))
            for item in history
        }
        assert len(signatures) == 50, f"Duplicate structured case in {group}"

        for item in existing:
            role_dir = "query" if item["role"] == "query" else "history"
            filename = f"SYN_{item['code'].replace('-', '_')}.docx"
            source = SOURCE_ROOT / group / role_dir / filename
            target = OUTPUT_ROOT / group / role_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest_rows.append(manifest_row(group, item, target, "existing-50"))

        for item in additions:
            filename = f"SYN_{item['code'].replace('-', '_')}.docx"
            target = OUTPUT_ROOT / group / "history" / filename
            make_doc(group, item, target)
            manifest_rows.append(manifest_row(group, item, target, "new-102"))

        for item in items:
            candidates = [other for other in items if other["code"] != item["code"] and other["role"] == "history"]
            nearest = max(candidates, key=lambda other: similarity(item, other))
            score = similarity(item, nearest)
            diversity_rows.append({
                "case_id": item["code"], "group": group, "role": item["role"],
                "diagnosis": item["diagnosis"], "phase": item["phase"],
                "age": item["age"], "ECOG": item["ecog"],
                "biomarkers": item["biomarkers"], "prior_treatment": item["prior"],
                "nearest_case_id": nearest["code"],
                "character_3gram_jaccard": f"{score:.4f}",
            })

    with open(OUTPUT_ROOT / "manifest.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)

    with open(OUTPUT_ROOT / "diversity_report.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=diversity_rows[0].keys())
        writer.writeheader()
        writer.writerows(diversity_rows)

    max_history_similarity = max(
        float(row["character_3gram_jaccard"])
        for row in diversity_rows if row["role"] == "history"
    )
    (OUTPUT_ROOT / "README.txt").write_text(
        "HemaGuide 合成病例相似性测试集（102份文档）\n"
        "==============================================\n"
        "白血病：50例历史病例 + 1例查询病例。\n"
        "淋巴瘤：50例历史病例 + 1例查询病例。\n"
        "原case_similarity_50保持不变；本目录为独立扩展版。\n"
        "新增52例历史病例：白血病26例，淋巴瘤26例。\n"
        f"历史病例中最高字符3-gram Jaccard相似度：{max_history_similarity:.4f}。\n"
        "manifest.csv为文件索引；diversity_report.csv记录最近病例及文本相似度。\n"
        "全部病例均为人工合成，不对应任何真实患者，不得用于临床决策。\n",
        encoding="utf-8",
    )
    print(f"Generated {len(manifest_rows)} documents in {OUTPUT_ROOT}")
    print(f"Maximum history-case similarity: {max_history_similarity:.4f}")


if __name__ == "__main__":
    main()
