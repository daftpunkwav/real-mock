/** resume 文案(简历管理:上传 / 列表 / 深度评价 / 原文件预览;key 用点分路径,zh-CN 为 key 源)。 */

export const resume = {
  // 页面骨架
  "page.loading": "加载中…",
  "head.eyebrow": "Resume",
  "head.title": "简历管理",

  // ResumeUploadArea:上传区
  "upload.parsing": "正在解析简历…",
  "upload.cta": "点击或拖拽上传简历",
  "upload.formats": "PDF · DOCX · MD · TXT · 最大 10MB",

  // ResumeList:列表
  "list.title": "我的简历",
  "list.count": "{count} 份",
  "list.empty": "暂无简历,请先上传一份",

  // ResumeListItem:列表项与操作条
  "item.chipActive": "投递",
  "item.scoreChip": "评分 {score}",
  "item.currentActive": "当前投递",
  "item.setActive": "设为投递",
  "item.analyzing": "评价中…",
  "item.analyze": "AI 深度评价",
  "item.delete": "删除",
  "item.deleteTitle": "删除简历",
  "item.deleteConfirm": "确定删除这一版「{name}」？同谱系其他版本会保留。",
  "item.versionChip": "v{n}",
  "item.latestIdle": "最新未投递",
  "item.uploadVersion": "上传新版本",

  // ResumeDetailPanel:深度评价区
  "detail.analyzingBanner": "评审 Agent 正在运行,完成后将自动刷新…",
  "detail.emptySelect": "选择一份简历后查看评价",
  "detail.none": "尚未生成深度评价",
  "detail.noneHint": "生成后将给出排版、字体与内容的完整审阅",
  "detail.start": "开始评价",

  // AnalyzeStageProgress: Agent 真实步骤
  "stage.waiting": "评审 Agent 正在决定下一步…",
  "stage.plan": "流程",
  "stage.parallel": "并行",
  "stage.parallelHint": "可与其他并行步骤批量执行",
  "stage.log": "执行过程",
  "stage.emptyLog": "等待第一条执行记录…",
  "stage.thinking": "思考",
  "stage.thinkingActive": "思考中…",
  "stage.thinkingDuration": "持续了 {seconds} 秒",
  "stage.toolName": "工具名",
  "stage.toolFallback": "工具",
  "stage.toolName.web_search": "检索信息",
  "stage.toolName.resume_overview": "阅读简历概览",
  "stage.toolName.resume_get_section": "查看简历分节",
  "stage.toolName.profile_list_sections": "列出档案分区",
  "stage.toolName.profile_get_section": "读取档案详情",
  "stage.toolName.github_get_user": "查看 GitHub 用户",
  "stage.toolName.github_list_repos": "列出 GitHub 仓库",
  "stage.toolName.github_get_repo": "查看 GitHub 仓库",
  "stage.toolName.github_get_readme": "阅读仓库 README",
  "stage.toolName.github_get_file": "阅读仓库源码",
  "stage.toolName.github_list_commits": "查看仓库提交",
  "stage.toolStatus.running": "进行中",
  "stage.toolStatus.done": "完成",
  "stage.toolStatus.error": "失败",
  "stage.sites": "检索站点",
  "stage.args": "调用参数",
  "stage.result": "调用结果",

  // AnalysisPanel:深度评价面板
  "analysis.mastheadTitle": "Agent 深度评价",
  "analysis.mastheadSub": "简历审阅意见",
  "analysis.tabsAria": "评价分区",
  "analysis.tab.overview": "总览",
  "analysis.tab.document": "版式与结构",
  "analysis.tab.projects": "项目深挖",
  "analysis.tab.interview": "面试演练",
  "analysis.tab.advice": "简历建议",
  "analysis.tab.career": "职涯与市场",

  // 深度评价维度标签(DIM_LABEL_KEYS)
  "dim.structure_clarity": "结构清晰度",
  "dim.visual_layout": "版式布局",
  "dim.typography": "字体可读性",
  "dim.impact_quantification": "成果量化",
  "dim.tech_depth": "技术深度",
  "dim.project_narrative": "项目叙事",
  "dim.role_fit": "岗位匹配",
  "dim.keyword_ats": "ATS 关键词",
  "dim.credibility": "可信度",
  "dim.seniority_signal": "职级信号",
  "dim.growth_signal": "成长潜力",
  "dim.collaboration_signal": "协作信号",

  // OverviewTab / ImpressionCards:总览
  "overview.narrative": "总评",
  "overview.seniorityPrefix": "职级判断 · ",
  "overview.roleFit": "岗位匹配",
  "overview.radar": "能力雷达",
  "overview.headlineTag": "一句话人设",
  "overview.impressionTag": "面试官 30 秒第一印象",
  "overview.notesTitle": "面试官工位随口点评",
  "overview.percentileTitle": "换算分位",
  "overview.percentileBefore": "由总分换算约 ",
  "overview.percentileAfter": "（换算分位）",
  "overview.percentileDisclaimer": "由总分单调换算，不是真实同岗样本。",
  "overview.seniorityLabel": "职级",
  "overview.dimTable": "维度一览",
  "overview.dimName": "维度",
  "overview.dimScore": "分数",
  "overview.dimBand": "档位",
  "overview.dimWeight": "权重",
  "overview.band.standout": "突出",
  "overview.band.solid": "扎实",
  "overview.band.mixed": "参差",
  "overview.band.weak": "偏弱",
  "overview.compareTitle": "版本差距",
  "overview.compareScores": "各版总分",
  "overview.compareDeltas": "相对上一版",
  "overview.compareOverall": "总分 {prev} → {curr}（{delta}）",
  "overview.compareDimsMissing": "上一版本缺少维度明细,仅对比总分。",
  "overview.compareOverlay": "雷达叠图",
  "overview.scaleLow": "偏低",
  "overview.scaleMid": "中位",
  "overview.scaleHigh": "偏高",

  // RadarChart / ScoreRing
  "radar.aria": "维度能力雷达图",
  "ring.aria": "综合得分 {score} 分",
  "ring.label": "综合",

  // ProjectsTab / ProjectCards:项目深挖
  "projects.evidence": "开源仓库取证",
  "projects.unknownRepo": "未知仓库",
  "projects.lastPush": "最近推送 {date}",
  "projects.verification": "宣称与仓库一致性",
  "projects.cardsTitle": "项目深挖卡片",
  "projects.highlight": "亮点",
  "projects.risk": "风险",
  "projects.mustAsk": "面试官必问",
  "projects.deepDive": "项目深挖点",

  // SkillTrustBoard(简历建议)/ SectionHeatmap(版式与结构)/ CareerPanel(职涯与市场)
  "advice.trustBoard": "技能核验三分板",
  "document.heatTitle": "分区审阅热力",
  "document.heatAria": "简历分区审阅",
  "trust.solid.title": "实证技能",
  "trust.solid.hint": "有项目与数字背书,面试可放心主讲",
  "trust.claimed.title": "仅罗列",
  "trust.claimed.hint": "只在技能清单出现,被追问容易露怯",
  "trust.missing.title": "岗位缺失",
  "trust.missing.hint": "目标岗高频要求,简历完全没提",
  "career.title": "职涯轨迹分析",
  "career.gaugeAria": "方向专注度 {score}",
  "career.gaugeLabel": "专注度",
  "career.gaps": "时间线疑点",

  // DocumentTab
  "document.layout": "排版与结构",
  "document.typography": "字体与可读性",
  "document.content": "内容深度",

  // InterviewTab:面试演练
  "interview.qaTitle": "问答推演卡",
  "interview.qaIntent": "考察意图",
  "interview.qaPoints": "参考答题要点",
  "interview.qaFollowUps": "可能的追问",
  "interview.predicted": "预测面试题",
  "interview.riskAreas": "面试易被打穿",

  // AdviceTab:简历建议
  "advice.strengths": "优势",
  "advice.weaknesses": "不足",
  "advice.redFlags": "风险点",
  "advice.improvements": "改进建议",
  "advice.coveredKeywords": "已覆盖关键词",
  "advice.suggestedKeywords": "建议补充",

  // CareerTab:职涯与市场
  "career.salary": "薪资定位参考",
  "career.companyFit": "公司层级匹配度",
  "career.market": "市场参考",

  // RewriteGallery:改写示例
  "rewrite.title": "改写示例",
  "rewrite.before": "改前",
  "rewrite.after": "改后",

  // ResumePreviewCard:右侧简历预览卡
  "previewCard.title": "简历预览",
  "previewCard.nameUnknown": "未解析姓名",
  "previewCard.open": "预览原文件",
  "previewCard.score": "AI 评分",
  "previewCard.summary": "摘要",
  "previewCard.skills": "技能",
  "previewCard.projects": "项目",
  "previewCard.projectUnnamed": "未命名项目",
  "previewCard.empty": "上传后显示预览",

  // ResumeOverviewCard / ResumeTipsCard:右侧概览与提示
  "overviewCard.title": "概览",
  "overviewCard.uploaded": "已上传",
  "overviewCard.scored": "已评分",
  "overviewCard.active": "当前投递:",
  "tips.title": "提示",
  "tips.first": "· 「投递简历」会关联到模拟面试与面试准备",
  "tips.second": "· 深度评价会联网检索岗位要求,并点评排版、字体与内容",
  "tips.third": "· 旧评价需重新点击「AI 深度评价」才会刷新新结构",

  // ResumeFilePreview / PreviewToolbar:原文件预览页
  "preview.nameFallback": "简历",
  "preview.pageAlt": "{name} 第 {page} 页",
  "preview.pages": "第 {current} / {total} 页",
  "preview.zoomOut": "缩小",
  "preview.zoomIn": "放大",
  "preview.fitWidth": "适应宽度",
  "preview.download": "下载",
  "preview.downloadFile": "下载文件",
  "preview.loadFailed": "预览加载失败，请下载后查看",
  "preview.unsupported": "该格式暂不支持在线预览，请下载后查看",

  // useResumeList / previewRoute:错误兜底与 toast
  "hook.loadFailed": "加载失败",
  "toast.uploaded": "简历已上传并解析",
  "toast.uploadedFallback": "简历已上传，但结构化解析未成功，目前只用了原文摘要。仍可做深度评价。",
  "toast.uploadFailed": "上传失败",
  "toast.listRefreshFailed": "操作已保存，但列表未能刷新，请重新加载页面。",
  "toast.parallelLimit": "最多同时并行评价 {count} 份简历，请等其中一份完成",
  "toast.analyzing":
    "正在为「{name}」生成深度评价（Agent 工具 + 联网检索），约需 2–4 分钟，最多可同时评价 {count} 份…",
  "toast.analyzingUnnamed": "正在生成深度评价（Agent 工具 + 联网检索），约需 2–4 分钟，最多可同时评价 {count} 份…",
  "toast.analyzeDone": "评价完成 · 综合评分 {score}",
  "toast.analyzeFailed": "分析失败",
  "toast.activated": "已设为投递简历",
  "toast.activateFailed": "设为投递失败",
  "toast.versionCap": "该谱系已有 {count} 个版本",
  "toast.deleted": "已删除",
  "toast.deleteFailed": "删除失败",
} as const;

export type ResumeMessageKey = keyof typeof resume;
