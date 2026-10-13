import csv
import tempfile
import unittest
from pathlib import Path

from generate_2026_data import CATEGORY_ORDER, build_report, classify_feedback, feedback_units


class ClassifyFeedbackTests(unittest.TestCase):
    def test_feedback_is_assigned_to_a_specific_theme(self):
        cases = [
            ("Ad Copy", "Change the age range to adults 18 to 35.", "Eligibility: age or participant group"),
            ("Video Creatives", "The study is for people 21 to 80 years old.", "Eligibility: age or participant group"),
            ("Ad Copy", "Add a question regarding current pregnancy status.", "Eligibility: age or participant group"),
            ("Landing Page", "Add the symptoms that qualify participants.", "Eligibility: diagnosis or symptoms"),
            ("Ad Creatives", "That wording about trauma is not accurate for our study.", "Eligibility: diagnosis or symptoms"),
            ("Ad Creatives", "Remove the exclusion about prior treatment.", "Eligibility: inclusion/exclusion criteria"),
            ("Ad Copy", "Update the criteria to exclude daily smokers.", "Eligibility: inclusion/exclusion criteria"),
            ("Landing Page", "No substance use disorders.", "Eligibility: inclusion/exclusion criteria"),
            ("Landing Page", "Live in New Jersey.", "Eligibility: inclusion/exclusion criteria"),
            ("Ad Copy", "No prior diagnoses.", "Eligibility: inclusion/exclusion criteria"),
            ("Ad Copy", "Diagnosed with schizophrenia.", "Eligibility: diagnosis or symptoms"),
            ("Ad Copy", "Do not exclude people based on their weight classification.", "Eligibility: inclusion/exclusion criteria"),
            ("Ad Copy", "We do not want to recruit individuals on GLP-1 medications.", "Eligibility: inclusion/exclusion criteria"),
            ("Video Creatives", "Clarify how many in-person visits are required.", "Study participation: visits, schedule, or duration"),
            ("Ad Copy", "Explain that participants receive MRI scans.", "Study participation: procedures or treatment"),
            ("Landing Page", "Add a sentence explaining the purpose of the study.", "Study details: purpose or design"),
            ("Screening Form", "Remove the redundant questions from the survey.", "Screening form: question count or flow"),
            ("Screening Form", "Change the wording of question 3.", "Screening form: question wording"),
            ("Screening Form", "Update the response options for question 3.", "Screening form: response options"),
            ("Screening Form", "Please add two new questions in place of question 12.", "Screening form: question count or flow"),
            ("Ad Copy", "The payment should be $100, not $150.", "Compensation: amount or accuracy"),
            ("Ad Creatives", "Make the payment less prominent.", "Compensation: prominence or presentation"),
            ("Landing Page", "Add 'no-cost' to the page.", "Compensation: prominence or presentation"),
            ("Ad Copy", "Replace this clinical acronym with plain language.", "Terminology: clinical or study terms"),
            ("Landing Page", "Rewrite this sentence so it is easier to understand.", "Copy: clarity and reading level"),
            ("Ad Creatives", "This line sounds too formal for teens.", "Copy: tone and audience fit"),
            ("Video Creatives", "It sounds ominous.", "Copy: tone and audience fit"),
            ("Ad Creatives", "The ads are too wordy.", "Copy: clarity and reading level"),
            ("Ad Copy", "Please revise this wording.", "Copy: word choice and phrasing"),
            ("Landing Page", "Add another line to the information section.", "Copy: content additions or removals"),
            ("Ad Creatives", "Any reason for removing that info?", "Copy: content additions or removals"),
            ("Ad Copy", "Could your teen's sun protection be better?", "Copy: tone and audience fit"),
            ("Ad Copy", "Join with other parents to improve your teen's health.", "Links or call to action"),
            ("Ad Copy", "Provide the campaign text in Spanish.", "Copy: translation or language consistency"),
            ("Ad Creatives", "The words are used too frequently in the ads.", "Copy: repetition or redundancy"),
            ("Ad Copy", "This phrase feels stigmatizing.", "Inclusive or non-stigmatizing language"),
            ("Ad Copy", "Add the required IRB approval language.", "Required compliance or disclosure language"),
            ("Ad Creatives", "Use an image showing a more diverse group of people.", "Visuals: imagery or representation"),
            ("Ad Creatives", "The graphics in the upper left hexagon look odd.", "Visuals: imagery or representation"),
            ("Ad Creatives", "These ads may look like clickbait.", "Required compliance or disclosure language"),
            ("Carousel", "They don't receive the $60 just for being in the study.", "Compensation: amount or accuracy"),
            ("Video Creatives", "Keep the music the same.", "Video: audio, pacing, or editing"),
            ("Video Creatives", "We like videos 3 and 4.", "Positive feedback"),
            ("Video Creatives", "Slow down the caregiver videos.", "Video: audio, pacing, or editing"),
            ("Ad Creatives", "I am not a fan of this blood pressure designation.", "Terminology: clinical or study terms"),
            ("Ad Creatives", "It feels very scammy.", "Required compliance or disclosure language"),
            ("Landing Page", "The questionnaire will be de-identified.", "Privacy, consent, or data-use language"),
            ("Ad Creatives", "We would like to emphasize serious injuries and traumatic brain injury.", "Eligibility: diagnosis or symptoms"),
            ("Ad Creatives", "They shouldn't depict them drinking heavily in uniform.", "Visuals: imagery or representation"),
            ("Ad Creatives", "There is already a soccer creative; consider another sport.", "Visuals: imagery or representation"),
            ("Ad Creatives", "Replace the outdated logo.", "Branding: logo or watermark"),
            ("Landing Page", "Correct the clinic address.", "Organization: location or institution"),
            ("Thank You page(s)", "Add the study team's email address.", "Contact information"),
            ("Landing Page", "The sign-up button should say Apply now.", "Links or call to action"),
            ("Ad Copy", "Please see attached.", "Attachment referenced — review"),
            ("Carousel", "Remove Carousel ads.", "Creative asset: scope, version, or placement"),
            ("Carousel", "We probably do not even need the carousel.", "Creative asset: scope, version, or placement"),
            ("Carousel", "What is it used for?", "Creative asset: scope, version, or placement"),
            ("Thank You page(s)", "Submission received.", "Confirmation or eligibility outcome messaging"),
            ("Landing Page", "The questionnaire will be de-identified.", "Privacy, consent, or data-use language"),
            ("Landing Page", "This study does not look at dopamine.", "Study details: purpose or design"),
            ("Landing Page", "Skin cancer risk often begins in the teenage years.", "Study details: purpose or design"),
            ("Video Creatives", "Increase the font size so the text is readable.", "Layout and readability"),
            ("Ad Copy", "Correct the spelling in the headline.", "Spelling or grammar"),
            ("Ad Copy", "The study title is incorrect; please update it.", "Study title or naming"),
            ("Carousel", "Please change it to 'Memory and Sleep Research Study'.", "Study title or naming"),
            ("Screening Form", "Looks good, thank you!", "Positive feedback"),
            ("Thank You page(s)", "Please add the hyperlink to the Thank You button.", "Links or call to action"),
            ("Video Creatives", "Could you use a different title?", "Study title or naming"),
            ("Ad Copy", "Specific suggestions attached in document.", "Attachment referenced — review"),
            ("Screening Form", "Only shown if ALL conditions are met.", "Screening form: question count or flow"),
            ("Ad Copy", "Please revise the opening paragraph.", "Copy: sentence or passage revision"),
            ("Ad Creatives", "Many ads don't explain what's involved in the study.", "Study participation: procedures or treatment"),
        ]

        for area, comment, expected in cases:
            with self.subTest(area=area, comment=comment):
                category = classify_feedback(area, comment)
                self.assertEqual(category, expected)
                self.assertIn(category, CATEGORY_ORDER)

    def test_specific_topics_take_precedence_over_general_copy(self):
        self.assertEqual(
            classify_feedback("Ad Copy", "Rewrite the diagnosis eligibility criteria."),
            "Eligibility: diagnosis or symptoms",
        )
        self.assertEqual(
            classify_feedback("Screening Form", "Update the branching logic for question 4."),
            "Screening form: question count or flow",
        )

    def test_feedback_headers_and_greetings_are_not_misclassified_as_edits(self):
        for fragment in ("Ads #5, 6, 7, and 8:", "Screening Form", "Hi Savannah,", "Dr.", "10aa.", "All video creatives need to include:", "Same thing as before."):
            with self.subTest(fragment=fragment):
                self.assertEqual(feedback_units(fragment), [])

    def test_report_build_uses_the_new_taxonomy(self):
        row = {
            "Created At": "01/15/26",
            "Notes": "Name: Client\n\nFor the ad copy, please list requested edits: Change the age range to adults 18 to 35.",
            "Edit Type": "Ad Copy",
            "Client Satisfaction Level": "4",
            "Feedback Source": "Study Team",
            "Section/Column": "Completed Edits",
            "Study ID": "STUDY-1",
        }
        second_row = {
            **row,
            "Created At": "01/16/26",
            "Notes": "Name: Client\n\nFor the ad copy, please list requested edits: We are seeking participants ages 40 to 60.",
            "Study ID": "STUDY-2",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "submissions.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=row.keys())
                writer.writeheader()
                writer.writerow(row)
                writer.writerow(second_row)

            report = build_report(csv_path)

        ad_copy = next(section for section in report["sections"] if section["edit_type"] == "Ad Copy")
        self.assertEqual(report["totalSubmissions"], 2)
        self.assertEqual(len(ad_copy["categories"]), 1)
        category = ad_copy["categories"][0]
        self.assertEqual((category["name"], category["count"]), ("Eligibility: age or participant group", 2))
        self.assertTrue(category["description"])
        self.assertEqual(len(category["examples"]), 2)


if __name__ == "__main__":
    unittest.main()
