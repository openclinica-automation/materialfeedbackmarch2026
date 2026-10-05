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
EMAIL_ADDRESS = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_NUMBER = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)")
AREA_CATEGORY_ADDITIONS = {
    "Physical Flyer": [
        "Eligibility Criteria Wording Change",
        "Incorrect Compensation Details",
        "Inappropriate Imagery",
        "Incorrect Terminology or Wording",
        "Layout or Formatting Issue",
        "Missing IRB/HIC Compliance Language",
        "Unclear Call to Action",
    ],
    "Thank You page(s)": [
        "Eligibility Criteria Wording Change",
        "Incorrect Compensation Details",
        "Incorrect Terminology or Wording",
        "Incorrect Study Participation Details",
        "Incorrect or Outdated Logo",
        "Unclear Call to Action",
        "Missing Contact Information",
        "Spelling or Grammar Error",
        "Layout or Formatting Issue",
    ],
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
    answer_end = answer_start + following_question.start() if following_question else len(notes)
    return notes[answer_start:answer_end].strip()


def feedback_units(answer):
    if not answer or re.fullmatch(r"(?:no|n/?a|none|no edits|no changes|not applicable)[.! ]*", answer, re.IGNORECASE):
        return []
    if re.match(r"^(?:(?:please )?see (?:the )?(?:attached|attachment|above)|attached (?:file|document|version))\b", answer, re.IGNORECASE):
        return []
    pieces = re.split(r"\n+", answer)
    units = []
    for piece in pieces:
        piece = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", piece).strip()
        if re.fullmatch(r"(?:file|video):\s*[\w./ -]+[.]?", piece, re.IGNORECASE):
            continue
        if piece and piece.lower().rstrip(":") not in {
            "see above", "see attached", "n/a", "none", "headlines", "headline",
            "primary text", "ad copy", "ad creatives", "general feedback",
            "changes requested", "reasoning", "overall", "thank you page",
        }:
            units.append(piece)
    return units


def redact_contact_details(value):
    value = EMAIL_ADDRESS.sub("[email removed]", value)
    return PHONE_NUMBER.sub("[phone removed]", value)


def classify_feedback(area, text, category_names):
    value = text.lower()

    def choose(*names):
        return next((name for name in names if name in category_names), None)

    def has(pattern):
        return re.search(pattern, value) is not None

    if has(r"\b(?:irb|hic|protocol number|irb number|institutional review board|approval language)\b"):
        return choose("Missing IRB/HIC Compliance Language")
    if has(r"\b(?:logo|watermark|branding)\b"):
        return choose("Incorrect or Outdated Logo", "Incorrect Location or Organization Info")
    if has(r"\b(?:spelling|spelled|typo|grammatical|grammar|punctuation|misspell)\b"):
        return choose("Spelling or Grammar Error", "Incorrect Terminology or Wording")
    if has(r"\b(?:email|e-mail|phone number|contact information|contact details)\b") and has(r"\b(?:add|include|missing|remove|change|update|correct)\b"):
        return choose("Missing Contact Information", "Incorrect Location or Organization Info")
    if has(r"\b(?:location|located|near|city|state|address|clinic|site name|institution|university|organization)\b"):
        return choose("Incorrect Location or Organization Info", "Incorrect Study Background or Description")
    if has(r"\b(?:image|photo|picture|visual|graphic|illustration|image library|image-library)\b"):
        if has(r"\b(?:unclear|confusing|does not|doesn't|not relatable|misleading|hard to understand)\b"):
            return choose("Unclear Visual Messaging", "Inappropriate Imagery")
        return choose("Inappropriate Imagery")
    if has(r"\b(?:compensation|payment|paid|stipend|incentive|earnings|dollar amount|\d[\d,]*(?:\.\d+)?\s*(?:%|percent|dollars))\b") or re.search(r"\$\s*\d", value):
        if has(r"\b(?:emphas|lead with|prominent|bold|larger|remove|take out|avoid|not mention|no amount|downplay|too much)\b"):
            return choose("Overemphasis on Compensation", "Incorrect Compensation Details")
        if has(r"\b(?:incorrect|wrong|update|change|correct|should be|instead|amount|\$|dollars|increase|decrease|remove)\b"):
            return choose("Incorrect Compensation Details", "Overemphasis on Compensation")
    if has(r"\b(?:title|headline|study name)\b") and has(r"\b(?:change|replace|remove|update|incorrect|wrong|should say|rename)\b"):
        return choose("Incorrect Study Title", "Incorrect Terminology or Wording")
    if has(r"\b(?:link|url|website|redirect)\b") and has(r"\b(?:broken|missing|doesn't work|does not work|incorrect|wrong|add|include|direct)\b"):
        return choose("Broken or Missing Link", "Unclear Call to Action")
    if has(r"\b(?:call to action|apply now|sign up|submit button|click here|button text|learn more)\b"):
        return choose("Unclear Call to Action")
    if has(r"\b(?:font|color|colour|spacing|layout|format|readab|text-heavy|text heavy|fit within|too small|too large|hard to read)\b"):
        if has(r"\b(?:font|color|colour)\b"):
            return choose("Font or Color Mismatch", "Layout or Formatting Issue")
        return choose("Layout or Formatting Issue")
    if has(r"\b(?:branching logic|branching|branch logic|branch|response option|answer option|question\s*#?\s*\d|q\s*\d|screening question|survey question)\b"):
        if has(r"\b(?:remove|delete|redundan|unnecessary|don't need|do not need|too many|excessive)\b"):
            return choose("Unnecessary or Excessive Questions", "Incorrect Question Wording")
        return choose("Incorrect Question Wording", "Unnecessary or Excessive Questions")
    if has(r"\b(?:visit|appointment|procedure|duration|how long|days|weeks|months|sessions|in-person|in person|remote|virtual|at-home|at home|travel|participat)\b") and has(r"\b(?:change|add|include|remove|update|incorrect|wrong|clarify|specify|replace|should|does not|doesn't|please|could|can we)\b"):
        return choose("Incorrect Study Participation Details", "Incorrect Study Background or Description")
    if has(r"\b(?:exclusionary|stigmatiz|discriminat|inclusive|exclusion criteria|exclude participants unfairly)\b"):
        return choose("Exclusionary Language in Eligibility Criteria", "Incorrect Study Eligibility Language", "Eligibility Criteria Wording Change")
    if has(r"\b(?:eligib|inclusion criteria|exclusion criteria|age range|age requirement|qualif|must be|criterion|criteria|state list|resident|reside|insurance is not required|not required to participate)\b"):
        if has(r"\b(?:wrong|incorrect|inaccurate|inconsistent|does not match|doesn't match|error)\b"):
            return choose("Eligibility Criteria Error", "Incorrect Study Eligibility Language", "Eligibility Criteria Wording Change")
        if has(r"\b(?:remove|delete|take out|replace|no longer need|should not include)\b"):
            return choose("Remove or Replace Eligibility Bullet", "Incorrect Study Eligibility Language", "Eligibility Criteria Wording Change")
        if has(r"\b(?:missing|add|include|should state|needs to say)\b"):
            return choose("Missing Eligibility Criteria Details", "Missing Eligibility Criteria Detail", "Missing Eligibility Criteria Statement", "Eligibility Criteria Wording Change")
        if area == "Landing Page" and has(r"\b(?:is this study for me|inclusion|exclusion|eligibility section)\b"):
            return choose("Incorrect Study Eligibility Language", "Eligibility Criteria Wording Change")
        return choose("Eligibility Criteria Wording Change", "Incorrect Question Wording")
    if area == "Screening Form" and has(r"\b(?:question|q\s*\d|item\s*\d|response option|answer option)\b"):
        if has(r"\b(?:remove|delete|redundan|unnecessary|don't need|do not need|too many|excessive)\b"):
            return choose("Unnecessary or Excessive Questions", "Incorrect Question Wording")
        return choose("Incorrect Question Wording", "Unnecessary or Excessive Questions")
    if has(r"\b(?:study background|study description|study purpose|study goal|study aims|why is this study|explain the study)\b"):
        return choose("Incorrect Study Background or Description", "Incorrect Study Participation Details")
    if area == "Screening Form" and has(r"\b(?:question|q\s*\d|item\s*\d|response option|answer option|state list|checkbox|select all|branching)\b"):
        if has(r"\b(?:remove|delete|redundan|unnecessary|don't need|do not need|too many|excessive)\b"):
            return choose("Unnecessary or Excessive Questions", "Incorrect Question Wording")
        return choose("Incorrect Question Wording", "Unnecessary or Excessive Questions")
    if has(r"\b(?:terminology|term|wording|reword|phrase|language|call it|refer to|replace .* with|small text|sentence|text says|word should|should read)\b"):
        return choose("Incorrect Terminology or Wording", "Incorrect Language in Ad Copy", "Incorrect Study Terminology", "Incorrect Question Wording")
    if has(r"\b(?:discuss|discussion|talk through|pushback|concern about making|would like to consider)\b"):
        return choose("Request for Discussion on Changes", "Incorrect Terminology or Wording")
    if has(r"\b(?:great|looks good|love|thank you|thanks|approved|acceptable|no further edits|ready to submit)\b") and not has(r"\b(?:change|remove|replace|add|update|please|could we|can you)\b"):
        return choose("Positive Feedback", "No Feedback Provided")
    return choose(
        {
            "Ad Copy": ("Incorrect Language in Ad Copy", "Incorrect Terminology or Wording"),
            "Ad Creatives": ("Incorrect Terminology or Wording", "Eligibility Criteria Wording Change"),
            "Carousel": ("Incorrect Terminology or Wording", "Eligibility Criteria Wording Change"),
            "Landing Page": ("Incorrect Study Background or Description", "Incorrect Terminology or Wording"),
            "Physical Flyer": ("Incorrect Terminology or Wording",),
            "Screening Form": ("Incorrect Question Wording", "Eligibility Criteria Wording Change"),
            "Thank You page(s)": ("Incorrect Terminology or Wording", "Incorrect Study Participation Details"),
            "Video Creatives": ("Incorrect Terminology or Wording", "Eligibility Criteria Wording Change"),
        }.get(area, ("Incorrect Terminology or Wording",))
    )


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
    all_category_names = {category["name"] for section in legacy_sections for category in section["categories"]}
    taxonomy_by_area = {}
    for section in legacy_sections:
        area = section["edit_type"]
        names = [category["name"] for category in section["categories"]]
        names.extend(name for name in AREA_CATEGORY_ADDITIONS.get(area, []) if name in all_category_names and name not in names)
        taxonomy_by_area[area] = names
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
            category_names = taxonomy_by_area[edit_type]
            if not units:
                category = "No Feedback Provided"
                units = [""]
                unit_categories = [category]
            else:
                fallback_by_area = {
                    "Ad Copy": "Incorrect Language in Ad Copy",
                    "Ad Creatives": "Incorrect Terminology or Wording",
                    "Carousel": "Incorrect Terminology or Wording",
                    "Landing Page": "Incorrect Study Background or Description",
                    "Physical Flyer": "Incorrect Terminology or Wording",
                    "Screening Form": "Incorrect Question Wording",
                    "Thank You page(s)": "Incorrect Terminology or Wording",
                    "Video Creatives": "Incorrect Terminology or Wording",
                }
                fallback_category = fallback_by_area.get(edit_type)
                if fallback_category not in category_names:
                    fallback_category = next((name for name in category_names if name != "No Feedback Provided"), "No Feedback Provided")
                unit_categories = [
                    classify_feedback(edit_type, unit, category_names) or fallback_category
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
        for category_name in category_names:
            records = issue_rows[area].get(category_name, [])
            csv_buffer = io.StringIO(newline="")
            writer = csv.writer(csv_buffer)
            writer.writerow(["Study ID", "Edit Type", "Edit Feedback", "Category", "Satisfaction Score", "Created At"])
            for record in records:
                writer.writerow([record["study_id"], area, record["feedback"], category_name, record["satisfaction"], record["created_at"]])
            csv_b64 = base64.b64encode(csv_buffer.getvalue().encode("utf-8-sig")).decode("ascii")
            example = next((record["feedback"].replace("\n", " ")[:220] for record in records if record["feedback"]), "")
            categories.append({
                "name": category_name,
                "count": len(records),
                "example": example,
                "csv_b64": csv_b64,
                "filename": f"2026_{re.sub(r'[^A-Za-z0-9]+', '_', area).strip('_')}_{re.sub(r'[^A-Za-z0-9]+', '_', category_name).strip('_')}.csv",
            })

        top3 = [
            {"cat": category["name"], "count": category["count"]}
            for category in sorted(categories, key=lambda category: (-category["count"], category["name"]))
            if category["count"] and category["name"] not in {"No Feedback Provided", "Positive Feedback"}
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
