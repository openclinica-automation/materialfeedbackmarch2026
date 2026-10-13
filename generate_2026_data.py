import argparse
import base64
import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


SATISFACTION_LABELS = {
    1: "Very Dissatisfied",
    2: "Dissatisfied",
    3: "Neutral",
    4: "Satisfied",
    5: "Very Satisfied",
}
SATISFACTION_COLORS = {
    1: "#D32F2F",
    2: "#F57C00",
    3: "#FBC02D",
    4: "#388E3C",
    5: "#1976D2",
}
EDIT_TYPE_COLORS = [
    "#2E5096",
    "#1976D2",
    "#0288D1",
    "#00838F",
    "#00695C",
    "#558B2F",
    "#F57F17",
    "#E65100",
]
AREA_QUESTION_PREFIXES = {
    "Ad Copy": "For the ad copy,",
    "Ad Creatives": "For the ad creatives,",
    "Carousel": "For the carousel,",
    "Landing Page": "For the landing page,",
    "Physical Flyer": "For the physical flyer,",
    "Screening Form": "For the screening form,",
    "Thank You page(s)": "For the Thank You page(s),",
    "Video Creatives": "For the video creatives,",
}
NEXT_QUESTION = re.compile(
    r"\n\n(?:For the (?:ad creatives|video creatives|carousel|ad copy|screening form|landing page|Thank You page\(s\))[,\w ]*|Do you have any overall comments|On a scale of 1 to 5|Are there any specific edits|Are there any overall comments)",
    re.IGNORECASE,
)
NOTES_END = re.compile(r"\n+(?:[-\u2014\u2013]{6,}\s*\n+This task was submitted through Customer Feedback|This task was submitted through Customer Feedback)", re.IGNORECASE)
EMAIL_ADDRESS = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_NUMBER = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)")
ASSET_HEADER = re.compile(
    r"^(?:ads?|videos?)\s*#?\s*\d+(?:\s*,?\s*(?:and|&)?\s*#?\d+)*\s*:?\s*$",
    re.IGNORECASE,
)

CATEGORY_ORDER = [
    "Eligibility: age or participant group",
    "Eligibility: diagnosis or symptoms",
    "Eligibility: inclusion/exclusion criteria",
    "Study participation: visits, schedule, or duration",
    "Study participation: procedures or treatment",
    "Study details: purpose or design",
    "Screening form: question count or flow",
    "Screening form: question wording",
    "Screening form: response options",
    "Compensation: amount or accuracy",
    "Compensation: prominence or presentation",
    "Terminology: clinical or study terms",
    "Copy: word choice and phrasing",
    "Copy: content additions or removals",
    "Copy: sentence or passage revision",
    "Copy: clarity and reading level",
    "Copy: tone and audience fit",
    "Copy: repetition or redundancy",
    "Copy: translation or language consistency",
    "Inclusive or non-stigmatizing language",
    "Privacy, consent, or data-use language",
    "Required compliance or disclosure language",
    "Visuals: imagery or representation",
    "Video: audio, pacing, or editing",
    "Branding: logo or watermark",
    "Organization: location or institution",
    "Contact information",
    "Links or call to action",
    "Creative asset: scope, version, or placement",
    "Confirmation or eligibility outcome messaging",
    "Layout and readability",
    "Study title or naming",
    "Spelling or grammar",
    "Positive feedback",
    "No Feedback Provided",
    "Attachment referenced — review",
    "Other requested edit — review",
]

THEME_DESCRIPTIONS = {
    "Eligibility: age or participant group": "Comments about the intended participants, such as age limits, life stage, or who the study is seeking.",
    "Eligibility: diagnosis or symptoms": "Comments clarifying which diagnoses, symptoms, or health experiences qualify participants.",
    "Eligibility: inclusion/exclusion criteria": "Comments adding, removing, or correcting a requirement that determines who can take part.",
    "Study participation: visits, schedule, or duration": "Comments about the number or timing of visits, time commitment, or study duration.",
    "Study participation: procedures or treatment": "Comments explaining what participants will do, receive, or experience during the study.",
    "Study details: purpose or design": "Comments clarifying the research question, purpose, background, or overall study design.",
    "Screening form: question count or flow": "Comments about adding or removing screener questions, their order, or conditional branching.",
    "Screening form: question wording": "Comments asking to clarify, correct, or rewrite a screening question.",
    "Screening form: response options": "Comments about the available answers or selection controls in a screening question.",
    "Compensation: amount or accuracy": "Comments correcting the payment or incentive amount, what it covers, or when it is received.",
    "Compensation: prominence or presentation": "Comments about how prominently payment is mentioned or visually emphasized.",
    "Terminology: clinical or study terms": "Comments replacing, explaining, or correcting medical, research, or other technical terminology.",
    "Copy: word choice and phrasing": "Specific suggestions to change a word or short phrase without changing the broader message.",
    "Copy: content additions or removals": "Requests to add, remove, or retain information, details, or sections in the copy.",
    "Copy: sentence or passage revision": "Requests to rewrite or revise a sentence, paragraph, headline, or other passage.",
    "Copy: clarity and reading level": "Comments that text is confusing, too complex, too wordy, or otherwise difficult to understand.",
    "Copy: tone and audience fit": "Comments about whether the wording feels appropriate, engaging, sensitive, or relatable to its audience.",
    "Copy: repetition or redundancy": "Comments that information or wording is repeated too often or unnecessarily.",
    "Copy: translation or language consistency": "Requests for translation or consistent language across materials.",
    "Inclusive or non-stigmatizing language": "Comments about respectful, inclusive wording and avoiding assumptions or stigmatizing language.",
    "Privacy, consent, or data-use language": "Comments explaining confidentiality, anonymity, consent, or how participant data is used.",
    "Required compliance or disclosure language": "Comments about required review-board, sponsor, policy, or other disclosure language.",
    "Visuals: imagery or representation": "Comments about the chosen images, people depicted, visual accuracy, or representation.",
    "Video: audio, pacing, or editing": "Comments about sound, voiceover, captions, timing, transitions, or video editing.",
    "Branding: logo or watermark": "Comments about the correct logo, branding, or watermark use.",
    "Organization: location or institution": "Comments correcting a clinic, institution, department, address, or other location reference.",
    "Contact information": "Comments adding or correcting an email address, phone number, or other way to contact the study team.",
    "Links or call to action": "Comments about links, buttons, redirects, or wording that guides the audience to take the next step.",
    "Creative asset: scope, version, or placement": "Comments about which creative files, versions, placements, or assets should be used or changed.",
    "Confirmation or eligibility outcome messaging": "Comments about submission confirmations or messages shown when screening is complete or someone is ineligible.",
    "Layout and readability": "Comments about visual layout, formatting, font, spacing, contrast, or text legibility.",
    "Study title or naming": "Comments correcting or changing the study title, name, or headline label.",
    "Spelling or grammar": "Comments identifying spelling, punctuation, or grammatical errors.",
    "Positive feedback": "Positive reactions or approval without a specific requested change.",
    "No Feedback Provided": "No substantive feedback was entered for this material.",
    "Attachment referenced — review": "The comment points to an attachment or tracked changes that are not available in this report; review the source material.",
    "Other requested edit — review": "A requested change is present, but the comment lacks enough context to assign it confidently to a specific theme.",
}


def parse_date(value):
    value = (value or "").strip()
    for pattern in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    return None


def month_keys(start, end):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year += 1
            month = 1


def load_legacy_taxonomy():
    report_html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
    match = re.search(r"const SECTIONS\s*=\s*(\[.*?\]);\s*\nconst CHART_DATA", report_html, re.DOTALL)
    if not match:
        raise ValueError("Could not find the archived report categories in index.html")
    return json.loads(match.group(1))


def extract_area_answer(notes, area):
    prefix = AREA_QUESTION_PREFIXES[area]
    position = notes.find(prefix)
    if position < 0:
        return ""
    answer_start = notes.find(":", position) + 1
    following_question = NEXT_QUESTION.search(notes[answer_start:])
    footer = NOTES_END.search(notes[answer_start:])
    answer_end = min(
        answer_start + following_question.start() if following_question else len(notes),
        answer_start + footer.start() if footer else len(notes),
    )
    return notes[answer_start:answer_end].strip()


def feedback_units(answer):
    if not answer or re.fullmatch(r"(?:no|n/?a|none|no edits|no changes|not applicable)[.! ]*", answer, re.IGNORECASE):
        return []
    if re.match(r"^(?:(?:please )?see (?:the )?(?:above|below)|same (?:as|comments?)|see comments below|see above feedback|see below|see spreadsheet|same comments as|see avove and fix for everything)\b", answer, re.IGNORECASE):
        return []
    units = []
    for paragraph in re.split(r"\n+", answer):
        pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"‘(])", paragraph)
        for piece in pieces:
            piece = re.sub(r"^\s*(?:[-*•✔✓✅☑]\ufe0f?|\d+[.)]|[oO]\s+(?=[A-Z]))\s*", "", piece).strip()
            if re.fullmatch(r"\d{1,2}[a-z]{0,2}[.:]?", piece, re.IGNORECASE):
                continue
            if re.fullmatch(r"(?:file|video):\s*[\w./ -]+[.]?", piece, re.IGNORECASE):
                continue
            if re.fullmatch(r"build\s*clinical[_\w.() -]*", piece, re.IGNORECASE):
                continue
            if re.fullmatch(r"[A-Z]{2,}\d+[A-Z0-9]*\s+edits?:", piece, re.IGNORECASE):
                continue
            if re.fullmatch(r"\d+[-_](?:tmplt|templt|template)[\w.-]*", piece, re.IGNORECASE):
                continue
            if re.fullmatch(r"[\w./() -]+\.(?:pdf|docx?|pptx?|xlsx?)(?:\([\w. -]+\))?", piece, re.IGNORECASE):
                continue
            if re.fullmatch(r"(?:see (?:above|below)|same (?:as|comments?|thing as before)|same comments as.*|see comments below|see above feedback|see below|see spreadsheet)[.! ]*", piece, re.IGNORECASE):
                continue
            if ASSET_HEADER.fullmatch(piece) or re.fullmatch(
                r"(?:headlines?\s*(?:#?\d+(?:\s*(?:and|,|&)\s*#?\d+)*)?|primary text|fast facts|faq|additional information(?: section)?|summary blurb(?: at top)?|in additional info|landing page|ad copy|ad creatives|video creatives|carousel|screening form|study background|is this study for me|overall feedback|edit down|what will happen if i participate in the study|so,? for example|for example|all (?:ad|video) creatives?(?: need to include| need to| must include)?|(?:dr|mr|ms|mrs)\.?)\s*:?",
                piece,
                re.IGNORECASE,
            ):
                continue
            if piece and piece.lower().rstrip(":") not in {
                "see above", "n/a", "none", "headlines", "headline",
                "primary text", "ad copy", "ad creatives", "general feedback",
                "changes requested", "reasoning", "overall", "thank you page",
            }:
                if re.fullmatch(r"(?:hi|hello|dear)\s+\w+[,:]?", piece, re.IGNORECASE):
                    continue
                if re.fullmatch(r"(?:they are requesting the following|please see above and fix for everything)[.!: ]*", piece, re.IGNORECASE):
                    continue
                units.append(piece)
    return units


def redact_contact_details(value):
    value = EMAIL_ADDRESS.sub("[email removed]", value)
    return PHONE_NUMBER.sub("[phone removed]", value)


def classify_feedback(area, text, category_names=None):
    value = text.lower()

    def has(pattern):
        return re.search(pattern, value) is not None

    if has(r"\b(?:great|looks good|love|we like|thank you|thanks|we appreciate your (?:interest|time|willingness)|approved|acceptable|no further edits|ready to submit)\b") and not has(r"\b(?:change|replace|remove|add|include|update|revise|reword|rewrite|please|could we|can you|should|needs to)\b"):
        return "Positive feedback"
    if has(r"\b(?:translate|translation|spanish|in spanish|language consistency|english only|only in english|bilingual)\b"):
        return "Copy: translation or language consistency"
    if has(r"\b(?:stigmatiz\w*|discriminat\w*|exclusionary|non.stigmatizing|inclusive language|offensive|insensitive|assum\w*|stereotyp\w*|every parent|not all parents)\b"):
        return "Inclusive or non-stigmatizing language"
    if has(r"\b(?:de.identif\w*|anonymous|anonymized|confidential\w*|privacy|protect(?:ing)? (?:participant|patient|personal) data)\b"):
        return "Privacy, consent, or data-use language"
    if has(r"\b(?:irb\w*|hic\w*|protocol number|institutional review board|approval language|principal investigator|pi name|department of defense|sponsored by|consent language|required disclaimer|not permitted|cannot use|must not use|scam advertisements?|scammy|clickbait|misleading|fraud|fakers?)\b"):
        return "Required compliance or disclosure language"
    if has(r"\b(?:compensation|payment|paid|stipend|incentive|earnings|dollar amount|money bags?|bag of money|no.cost|free|at no cost)\b") or re.search(r"\$\s*\d|\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent|dollars)\b", value):
        return "Compensation: prominence or presentation" if has(r"\b(?:no.cost|free|at no cost)\b") else (
            "Compensation: prominence or presentation"
            if has(r"\b(?:emphas|lead with|prominent|bold|larger|downplay|too much|overemphas|remove|take out|avoid|not mention|no amount)\b")
            else "Compensation: amount or accuracy"
        )
    if has(r"\b(?:email|e-mail|phone number|contact information|contact details|contact them|contact method)\b"):
        return "Contact information"
    if has(r"\b(?:logo|watermark|branding|brand guidelines?)\b"):
        return "Branding: logo or watermark"
    if has(r"\b(?:images?|imagery|photo|photograph|picture|visuals?|graphics?|illustration|cartoon|image library|image-library|actor|people images|younger people|older people|older men|racially diverse|ethnicity of individuals portrayed|ethnic background|freckled|landscape|hearing aid|looks? (?:a little )?(?:strange|awkward|uncanny)|uncanny valley|ai.generated|ai look|motion|sleeping on the couch|depict\w*|uniform|drinking heavily|soccer|sport|outdoor activity|mother.child|parent.child|leaf behind|bong|bottle from background|person alone|older woman alone|video footage|black dots|foreground|human reading|looks? odd)\b"):
        return "Visuals: imagery or representation"
    if area in {"Video Creatives", "Ad Creatives", "Carousel"} and has(r"\b(?:music|sound|audio|voiceover|voice over|pacing|transition|editing|second frame|frame|slide|lip.read|captions?|subtitles?|speech|slow down|too quickly|screen to screen)\b"):
        return "Video: audio, pacing, or editing"
    if has(r"\b(?:spelling|spelled|typo|grammatical|grammar|punctuation|misspell)\b"):
        return "Spelling or grammar"
    if (has(r"\b(?:titles?|headlines?|study name)\b") or has(r"\b(?:say|change|replace|rename)\b.{0,60}\bresearch study\b")) and has(r"\b(?:change|replace|remove|update|incorrect|wrong|should say|rename|revise|say|different)\b"):
        return "Study title or naming"
    if has(r"\b(?:link|hyperlink|url|website|redirect|unable to access|call to action|apply now|sign up|submit button|click(?:ing)? here|click to|places to click|button text|learn more|interested(?:\?|\b)|is this study for me|join (?:us|the|a|other|with)|help (?:cancer )?researchers?)\b"):
        return "Links or call to action"
    if has(r"\b(?:submission received|thank you for submitting|response recorded|successfully submitted|submission confirmation|appears you are ineligible|screening is not yet complete|incomplete screening|congratulations?)\b"):
        return "Confirmation or eligibility outcome messaging"
    if (area == "Carousel" and has(r"\bwhat is it used for\b")) or (has(r"\b(?:remov\w*|delet\w*|replace|swap|version|versions|placement|placements|do not (?:even )?need|don't (?:even )?need|no longer need|what is it used for)\b") and has(r"\b(?:ads?|carousel|video|creatives?|campaign|asset|headline|image|file)\b")):
        return "Creative asset: scope, version, or placement"
    if has(r"\b(?:version 1|version 2|prefer version|version comparison)\b"):
        return "Creative asset: scope, version, or placement"
    if has(r"\b(?:branching logic|branching|branch logic|conditional logic|skip logic|survey flow|question order|only shown if|conditions? are met)\b") and has(r"\b(?:question|screener|screening|survey|form|response|answer|conditions?)\b"):
        return "Screening form: question count or flow"
    if has(r"\b(?:response options?|answer options?|answers? to the screener|screener answers?|multiple.choice|checkbox(?:es)?|radio buttons?|dropdowns?|drop.downs?|select all)\b") and has(r"\b(?:question|screener|screening|survey|form|option|answer|select)\b"):
        return "Screening form: response options"
    if area == "Screening Form" and has(r"\b(?:add|include|insert|remove|delete|replace)\b") and has(r"\b(?:questions?|items?|fields?)\b"):
        return "Screening form: question count or flow"
    if area == "Screening Form" and has(r"\b(?:remove|delete|redundan|unnecessary|don't need|do not need|too many|excessive)\b") and has(r"\b(?:questions?|items?|fields?|screening|survey)\b"):
        return "Screening form: question count or flow"
    if (
        re.search(r"\b\d{1,3}\s*(?:to|-)\s*\d{1,3}\s*years? old\b", value)
        or (
            has(r"\b(?:target population|intended audience|age range|age requirement|ages?\b|target age|gender criteria|male|female|men|women|teens?|teenagers?|adolescents?|youth|children|parents?|caregivers?|older adults?|healthy volunteers?|pregnan\w*|breastfeed\w*|third trimester)\b")
            and has(r"\b(?:eligib\w*|qualif\w*|participant|include|exclude|criteria|age|target|should|must|need|only|audience|population|status|question|redundan\w*|looking for|seeking|recruit)\b")
        )
    ):
        return "Eligibility: age or participant group"
    if has(r"\b(?:diagnos\w*|symptoms?|trauma|injur\w*|coma|traumatic brain injury|disorder|condition|disease|depression|anxiety|schizophrenia|ptsd|bipolar|autis\w*|adhd|low mood|pain|cancer|diabetes|memory difficulties|memory and concentration|menopause|blood pressure)\b") and has(r"\b(?:eligib\w*|qualif\w*|participant|include|exclude|criteria|must|need|target|population|should|only|change|replace|add|remove|mention|describe|say|accurate|experience|experiencing|who)\b"):
        return "Eligibility: diagnosis or symptoms"
    if has(r"\b(?:ineligible|not eligible|exclusion\w*|inclusion\w*|eligib\w*|qualif\w*|criterion|criteria|state list|resident|resid\w*|live in|lives in|living in|insurance is not required|not required to participate|required to participate|cigarettes? per day|smok\w*|substances?|cannabis|non.smoker|medical conditions?|hearing aid experience|parent or child qualify|child qualifies|at least 1 in.person visit|missing criteria|upper limit|personal smartphone|smartphone access|no prior diagnos\w*|no history of|no untreated|no substance use disorders?|untreated sleep apnea|recruit individuals|want to recruit|phone screening|glp.1|wegovy|ozempic|zepbound|mounjaro|weight classification|selection bias|narrow pool)\b"):
        return "Eligibility: inclusion/exclusion criteria"
    if has(r"\b(?:diagnos\w*|symptoms?|traumat\w*|injur\w*|coma|traumatic brain injury|schizophrenia|ptsd|bipolar|autis\w*|adhd|depression|anxiety|disease|disorder|condition|pain|memory difficulties|memory and concentration)\b"):
        return "Eligibility: diagnosis or symptoms"
    if has(r"\b(?:high potential for fraud|fraud prevention|cannot (?:include|display|show)|do not display|don't display)\b") and has(r"\b(?:screen|answer|response|ad|landing page)\b"):
        return "Screening form: response options"
    if area == "Screening Form" and has(r"\b(?:questions?|q\s*\d|items?\s*\d|response options?|answer options?|fields?|screening|checkbox|select all|gender|name of child|parent.guardian)\b"):
        return "Screening form: question wording"
    if has(r"\b(?:study background|study description|study purpose|study goal|study aims|purpose.{0,20}study|goal.{0,20}study|aims?.{0,20}study|why is this study|explain the study|research question|clinical trial is for|what the study is about|study.{0,30}(?:measure|investigate|look at)|(?:requisite|enough|sufficient) amount of information|information to potential participants|concept that describes|concept is an important factor|brain processes|measuring.{0,40}research|research.{0,30}measure|traditional exercise|intolerance of uncertainty|confused with another study|findings|eating behavior|eating patterns|pharmacotherapies|melanoma|skin cancer risk|sun exposure|sunburns)\b"):
        return "Study details: purpose or design"
    if has(r"\b(?:visits?|appointments?|duration|how long|days|weeks|months|sessions|multi-session|in-person|in person|remote|virtual|at-home|at home|travel|schedule|time commitment|contact them|study involves|follow.up)\b"):
        return "Study participation: visits, schedule, or duration"
    if has(r"\b(?:procedure|treatment|mri|blood draw|lab work|medication|intervention|therapy|device|wearable|apps?|study activity|what participants do|participat|what[’']s involved|what is involved|what the study is|what will happen if i participate|interviews?|recorded|receiv\w*|transportation|parking voucher|travel assistance|measuring|measures)\b"):
        return "Study participation: procedures or treatment"
    if has(r"\b(?:location|located|near|city|state|address|clinic|sites?|site name|institution|university|organization|county|target area|charleston|skyline|new brunswick|pittsburgh|houston|bethesda|austin|conducted (?:in|at)|research site)\b"):
        return "Organization: location or institution"
    if has(r"\b(?:terminology|clinical term|medical term|medical terminology|technical term|acronym|jargon|refer to|call it|term for|bp wording|blood pressure|moderately high|dopamine|clinical trial|not a clinical trial)\b") or re.search(r"\bbp\b", value):
        return "Terminology: clinical or study terms"
    if has(r"\b(?:redundan\w*|repeated|repeats|too frequently|used frequently|used often|repetitive)\b"):
        return "Copy: repetition or redundancy"
    if has(r"\b(?:font|colors?|colours?|palette|spacing|layout|formatting|formatted|numbering|numbered|readab\w*|text.heavy|fit within|too small|too large|hard to read|template\w*|same line|line break|fit on one line|negative space|white space|redesign|notes app|reminders app)\b"):
        return "Layout and readability"
    if has(r"\b(?:tone|sounds? (?:too|more|less|odd|ominous|strange|awkward)|not relatable|relatable|audience fit|too formal|too casual|sensitive|appropriate for|could your|do you worry|is your (?:child|teen)|engaging|appealing)\b"):
        return "Copy: tone and audience fit"
    if has(r"\b(?:unclear|confusing|hard to understand|easier to understand|plain language|reading level|readability|clearer|clarify|wordy)\b"):
        return "Copy: clarity and reading level"
    if has(r"\b(?:add|include|insert|remov\w*|delet\w*|omit|mention)\b") and has(r"\b(?:bullet|line|detail|information|info|content|section|item|list|only|additional|missing|not enough|more text|creatives?)\b"):
        return "Copy: content additions or removals"
    if has(r"\b(?:attached|attachment|tracked changes|uploading as tracked|suggestions? (?:in|attached to) (?:the )?document|added in the attachment)\b"):
        return "Attachment referenced — review"
    if has(r"\b(?:wording|reword|phrase|words?|verbiage|term|say something|in the vein of|say.{0,20}(?:to|instead)|to say)\b"):
        return "Copy: word choice and phrasing"
    if has(r"\b(?:language|copy|text|sentence|blurb|paragraph|clunky|doesn't flow|does not flow|rewrite|revise)\b"):
        return "Copy: sentence or passage revision"
    if has(r"\b(?:change|replace|remove|add|include|update|revise|reword|rewrite|please|could we|can we|should|needs to|suggest)\b"):
        return "Copy: sentence or passage revision"
    if area == "Screening Form":
        return "Screening form: question wording"
    if area in {"Ad Copy", "Ad Creatives", "Carousel", "Landing Page", "Video Creatives"} and has(r"\b(?:headline|ad|copy|slide|frame|video|creative|campaign|study|participant|word|text|phrase|term|accurate|incorrect|not appropriate)\b"):
        return "Copy: sentence or passage revision"
    return "Other requested edit — review"


def build_report(input_path):
    with input_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"Created At", "Notes", "Edit Type", "Client Satisfaction Level", "Feedback Source", "Section/Column"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        submissions = []
        for row in reader:
            created = parse_date(row.get("Created At"))
            notes = (row.get("Notes") or "").lstrip()
            if created and created.year == 2026 and notes.startswith("Name:"):
                submissions.append((created, row))

    if not submissions:
        raise ValueError("No 2026 form-submission rows found. Expected Notes to begin with 'Name:'.")

    submissions.sort(key=lambda item: item[0])
    legacy_sections = load_legacy_taxonomy()
    taxonomy_by_area = {section["edit_type"]: CATEGORY_ORDER for section in legacy_sections}
    start_date, end_date = submissions[0][0], submissions[-1][0]
    months = list(month_keys(start_date, end_date))
    monthly_submissions = Counter()
    monthly_ratings = defaultdict(list)
    edit_type_counts = Counter()
    monthly_edit_types = defaultdict(Counter)
    satisfaction_counts = Counter()
    status_counts = Counter()
    source_counts = Counter()
    area_submissions = Counter()
    area_ratings = defaultdict(list)
    area_monthly = defaultdict(Counter)
    issue_rows = defaultdict(lambda: defaultdict(list))
    uncategorized_by_area = Counter()
    rated_count = 0
    unrated_count = 0

    for created, row in submissions:
        month = created.strftime("%Y-%m")
        monthly_submissions[month] += 1

        edit_types = [item.strip() for item in (row.get("Edit Type") or "").split(",") if item.strip()]
        normalized_edit_types = []
        for edit_type in edit_types:
            if edit_type == "Printout Physical Flyer (if applicable)":
                edit_type = "Physical Flyer"
            normalized_edit_types.append(edit_type)
            edit_type_counts[edit_type] += 1
            monthly_edit_types[edit_type][month] += 1

        satisfaction_match = re.match(r"\s*([1-5])(?:\s*[-\u2013])?", row.get("Client Satisfaction Level") or "")
        if satisfaction_match:
            score = int(satisfaction_match.group(1))
            satisfaction_counts[score] += 1
            monthly_ratings[month].append(score)
            for edit_type in normalized_edit_types:
                area_ratings[edit_type].append(score)
            rated_count += 1
        else:
            unrated_count += 1

        status_counts[(row.get("Section/Column") or "").strip() or "Not specified"] += 1
        source = (row.get("Feedback Source") or "").strip()
        if "IRB" in source:
            source = "IRB Feedback"
        elif "Study Team" in source:
            source = "Study Team Feedback"
        else:
            source = "Not specified"
        source_counts[source] += 1

        for edit_type in set(normalized_edit_types):
            if edit_type not in taxonomy_by_area:
                continue
            area_submissions[edit_type] += 1
            area_monthly[edit_type][month] += 1
            answer = extract_area_answer(row.get("Notes") or "", edit_type)
            units = feedback_units(answer)
            if not units:
                category = "No Feedback Provided"
                units = [""]
                unit_categories = [category]
            else:
                unit_categories = [
                    classify_feedback(edit_type, unit)
                    for unit in units
                ]

            grouped_units = defaultdict(list)
            for unit, category in zip(units, unit_categories):
                if category is None:
                    uncategorized_by_area[edit_type] += 1
                else:
                    grouped_units[category].append(redact_contact_details(unit))
            satisfaction_value = row.get("Client Satisfaction Level") or ""
            for category, category_units in grouped_units.items():
                issue_rows[edit_type][category].append({
                    "study_id": row.get("Study ID", ""),
                    "created_at": created.isoformat(),
                    "satisfaction": satisfaction_value,
                    "feedback": "\n".join(unit for unit in category_units if unit),
                })

    ordered_edit_types = sorted(edit_type_counts, key=lambda item: (-edit_type_counts[item], item))
    edit_types_data = [
        {
            "name": name,
            "count": edit_type_counts[name],
            "color": EDIT_TYPE_COLORS[index % len(EDIT_TYPE_COLORS)],
            "monthly": [monthly_edit_types[name][month] for month in months],
        }
        for index, name in enumerate(ordered_edit_types)
    ]
    month_data = [
        {
            "month": month,
            "submissions": monthly_submissions[month],
            "avgSatisfaction": round(sum(monthly_ratings[month]) / len(monthly_ratings[month]), 2)
            if monthly_ratings[month]
            else None,
            "ratedSubmissions": len(monthly_ratings[month]),
        }
        for month in months
    ]
    satisfaction_data = [
        {
            "score": score,
            "label": SATISFACTION_LABELS[score],
            "count": satisfaction_counts[score],
            "color": SATISFACTION_COLORS[score],
        }
        for score in range(1, 6)
    ]
    average_satisfaction = (
        round(sum(score * count for score, count in satisfaction_counts.items()) / rated_count, 2)
        if rated_count
        else None
    )

    report_sections = []
    for section_index, legacy_section in enumerate(legacy_sections):
        area = legacy_section["edit_type"]
        category_names = taxonomy_by_area[area]
        categories = []
        populated_categories = [
            name for name in category_names if issue_rows[area].get(name)
        ]
        for category_name in populated_categories:
            records = issue_rows[area].get(category_name, [])
            csv_buffer = io.StringIO(newline="")
            writer = csv.writer(csv_buffer)
            writer.writerow(["Study ID", "Edit Type", "Edit Feedback", "Category", "Satisfaction Score", "Created At"])
            for record in records:
                writer.writerow([record["study_id"], area, record["feedback"], category_name, record["satisfaction"], record["created_at"]])
            csv_b64 = base64.b64encode(csv_buffer.getvalue().encode("utf-8-sig")).decode("ascii")
            example = next((record["feedback"].replace("\n", " ")[:220] for record in records if record["feedback"]), "")
            examples = []
            seen_examples = set()
            for record in records:
                text = " ".join(record["feedback"].split())
                if not text:
                    continue
                key = text.casefold()
                if key in seen_examples:
                    continue
                seen_examples.add(key)
                examples.append(text[:220])
                if len(examples) == 3:
                    break
            categories.append({
                "name": category_name,
                "count": len(records),
                "description": THEME_DESCRIPTIONS[category_name],
                "examples": examples,
                "example": example,
                "csv_b64": csv_b64,
                "filename": f"2026_{re.sub(r'[^A-Za-z0-9]+', '_', area).strip('_')}_{re.sub(r'[^A-Za-z0-9]+', '_', category_name).strip('_')}.csv",
            })

        legacy_order = {name: index for index, name in enumerate(category_names)}
        categories.sort(key=lambda category: (-category["count"], legacy_order[category["name"]]))

        top3 = [
            {"cat": category["name"], "count": category["count"]}
            for category in sorted(categories, key=lambda category: (-category["count"], category["name"]))
            if category["count"] and category["name"] not in {"No Feedback Provided", "Positive feedback"}
        ][:3]
        section_months = []
        for month in months:
            scores = [score for _, row in submissions
                      if month == (parse_date(row.get("Created At")) or start_date).strftime("%Y-%m")
                      and area in ["Physical Flyer" if item.strip() == "Printout Physical Flyer (if applicable)" else item.strip()
                                   for item in (row.get("Edit Type") or "").split(",")]
                      for score_match in [re.match(r"\s*([1-5])", row.get("Client Satisfaction Level") or "")]
                      if score_match for score in [int(score_match.group(1))]]
            section_months.append({
                "month": month,
                "volume": area_monthly[area][month],
                "satisfaction": round(sum(scores) / len(scores), 2) if scores else None,
            })
        report_sections.append({
            "edit_type": area,
            "count": area_submissions[area],
            "avg_sat": round(sum(area_ratings[area]) / len(area_ratings[area]), 2) if area_ratings[area] else 0,
            "color": legacy_section.get("color", EDIT_TYPE_COLORS[section_index % len(EDIT_TYPE_COLORS)]),
            "top3": top3,
            "categories": categories,
            "uncategorized_count": uncategorized_by_area[area],
            "section_chart": {
                "months": [item["month"] for item in section_months],
                "volume": [item["volume"] for item in section_months],
                "satisfaction": [item["satisfaction"] for item in section_months],
            },
        })

    return {
        "year": 2026,
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "totalSubmissions": len(submissions),
        "editTypeCount": len(edit_type_counts),
        "unspecifiedEditTypeSubmissions": sum(
            1 for _, row in submissions if not (row.get("Edit Type") or "").strip()
        ),
        "ratedSubmissions": rated_count,
        "unratedSubmissions": unrated_count,
        "averageSatisfaction": average_satisfaction,
        "months": month_data,
        "editTypes": edit_types_data,
        "satisfaction": satisfaction_data,
        "statuses": [
            {"name": name, "count": count}
            for name, count in sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "sources": [
            {"name": name, "count": count}
            for name, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "uncategorizedFeedbackItems": sum(uncategorized_by_area.values()),
        "sections": report_sections,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate aggregate dashboard data from an Asana export.")
    parser.add_argument("csv_file", type=Path, help="Asana project tasks CSV export")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("report-2026-data.json"),
        help="Output JSON path (default: report-2026-data.json beside this script)",
    )
    args = parser.parse_args()

    report = build_report(args.csv_file)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {report['totalSubmissions']} 2026 submissions to {args.output}")


if __name__ == "__main__":
    main()
