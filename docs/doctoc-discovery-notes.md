# DocToc — Discovery Notes

## المشكلة المرصودة

مستودعات Markdown الكبيرة (مستندات، READMEs متعددة، أطر) تعتمد على فهرس محتويات (TOC) لتصفح الأقسام، لكن توليد الفهرس يدويًا أو بأدوات هشّة يؤدي إلى «انجراف الفهرس» (TOC drift): روابط تُشير إلى عناوين محذوفة أو معاد تسميتها، فتفشل دون إنذار. الأدوات القائمة:

| أداة | ضعفها |
|---|---|
| `markdown-toc` (doctoc CLI، 1.8k stars) | 65 issue مفتوح: روابط خاطئة عند عناوين فيها links (#158, #169)، inline code يُحذف رغم الأعلام (#170)، `no-firsth1` يسبب «undefined» (#168)، headers داخل comments تُدرج (#178)، تعديل front-matter (#151)، أخطاء في esbuild/vite (#182)، لا فحص انجراف في CI |
| `mdtoc` (Rust) | جيد لكن يدمج فهارس متعددة بأرقام مكررة، لا يوجد وضع `check` للتحقق من التزام الفهرس بدون تعديل (استخدم في CI يدويًا عبر diff) |
| `gh-md-toc` | سكربت bash خارجي، يعتمد على API/متصفح أحيانًا، غير مناسب للتشغيل المحلي السريع |
| `vscode-markdown` (extension) | يولّد TOC لكنها ميزة داخل محرر؛ انجراف عند التعديل اليدوي خارج المحرر؛ vscode-markdown issue #301: `#` داخل code block يكسر الفهرس |
| `[TOC]` marker (stackedit/markdown-it) | عرض فقط في المحرر؛ لا يُثبّت في الملف، لا يصلح للمستودعات |

## Who / Why / Gap

- **من**: مشرفو مستودعات docs، فرق platform التي تُشغّل CI checks على docs، كاتبو technical writing بالـ Markdown.
- **كيف الآن**: توليد TOC مرة واحدة ثم نسيانها (انجراف)، أو سكربتات bash هشة، أو Node CLI مع تبعيات قديمة (remarkable CVE-156).
- **الفجوة**: لا توجد أداة Python بلا تبعيات تجمع (1) slug مطابق GitHub GFM، (2) تجاهل headings داخل fenced code blocks وHTML comments، (3) markers مُثبتة في الملف `<!--TOC-->...<!--/TOC-->`، (4) وضع `check` حتمي يعيد كود فشل في CI عند الانجراف دون تعديل الملف، (5) `--validate-links` للتحقق من أن كل رابط TOC يشير فعليًا إلى عنوان موجود.

## Project Thesis

For maintainers of Markdown documentation who suffer from silently broken TOC links, DocToc provides a zero-dependency CLI that generates and syncs GitHub-compatible tables of contents inside markers and — unlike markdown-toc/mdtoc — adds a deterministic `check` mode for CI and per-file link validation, by parsing fenced/indented code blocks and HTML comments correctly.

## Differentiators (Structural)

1. **GitHub slug fidelity**: نفس خوارزمية GitHub (lowercase، space→`-`، strip punctuation، strip accents، dedup بـ `-1, -2, ...`) — موثقة وتختبر ضد صفحات GitHub الفعلية.
2. **Correct fenced/HTML-aware parsing**: headings داخل fenced code blocks (متطابقة الفاصل ` ``` `+) وHTML comments `<!-- -->` وsetext headings تُعالج بصحيح CommonMark.
3. **Check mode**: `doctoc check` لا يعدّل الملفات ويعيد exit 1 عند أي انجراف — مثالي لـ CI بدون side effects.
4. **Link validation**: `--validate-links` يتحقق أن كل سطر TOC يشير لعنوان موجود فريد (يدرك dedup suffix).
5. **Markers**: `<!--TOC-->...<!--/TOC-->` قابلة للتخصيص؛ ملفات بلا markers تُنشأ block تلقائيًا (اختياري).
6. Zero dependencies، Python stdlib فقط، exit codes موثقة.

## الأخطار (Threat Model مبدئي)

- path traversal عبر glob patterns مثل `../../etc` → نقيّد المسارات بمسار العمل ونرفض absolute/.. خارج cwd في وضع write.
- ملف كبير جدًا أو غير قابل للقراءة (binary) → رفض صريح مع رسالة.
- symlinks الحلقي → نتبع بحد أقصى عمق.
- TOC موجود بلا marker → لا نعدل الملف إلا بـ --create-block صريح (حماية من الكتابة العرضية).
- headings بمحتوى خطير (HTML raw في العناوين) → نُجري stripping آمن ونرفض العناوين الفارغة بعد التنظيف.

## قرار النطاق (Must/Should/Could)

- Must: تحليل headings (ATX + setext)، fenced code block awareness، GitHub slug، markers، generate + check modes، dedup anchors، multiple files، exit codes.
- Should: --max-depth، --validate-links، --min-level، dry-run، JSON report.
- Could: indented code block awareness (GFM لا يعتبره code block في headings detection لكن...)، custom slug algorithm.
- ملاحظة: `doctoc` اسم CLI موجود في npm؛ نسمي CLI `doctoc` في Python world بلا تعارض عملي (pip script)، أو نكتفي بالاسم المستودعي doctoc.

## خوارزمية GitHub slug (موثقة من pulldown-cmark-toc src/slug.rs — GitHubSlugifier)

1. lowercase.
2. space → `-`.
3. strip كل ما ليس `[\w\- ]` (الأحرف المميزة/الإيموجي تختفي).
4. dedup: تكرار slug يحصل على suffix `-1`, `-2`, ... (العداد يبدأ من 0: أول ظهور بلا suffix، الثاني `-1`).

ملاحظة: GitHub الحقيقي أيضًا يزيل accents عبر Unicode normalization (NFD ثم إزالة combining marks) — نضيفها لأنها موثقة في markdown-it-anchor spec لـ GitHub.

## ملاحظات إضافية من بحث badging/issues
- markdown-toc: multiple `<!--toc-->` تكسر (issue #198)، front-matter يُعدل (issue #151)، no-firsth1 يسبب undefined (issue #168)، maxdepth لا يعمل (issue #174)، headers داخل comments تُدرج (issue #178).
- GFM spec لا يوثق slugification — الفجوة هي نفسها فرصتنا (اختلاف غامض بين منصات = سلوك GitHub موحد يجب أن تكون الأداة متطابقة معه فقط + قابلة للتبديل).
