from doajtest.helpers import DoajTestCase
from doajtest.fixtures import ApplicationFixtureFactory

import re, time
from copy import deepcopy

from portality import models
from portality.formcontext import formcontext
from portality import lcc

from werkzeug.datastructures import MultiDict
from nose.tools import assert_raises

#####################################################################
# Mocks required to make some of the lookups work
#####################################################################

@classmethod
def editor_group_pull(cls, field, value):
    eg = models.EditorGroup()
    eg.set_editor("eddie")
    eg.set_associates(["associate", "assan"])
    eg.set_name("Test Editor Group")
    return eg

mock_lcc_choices = [
    (u'H', u'Social Sciences'),
    (u'HB1-3840', u'--Economic theory. Demography')
]

def mock_lookup_code(code):
    if code == "H": return "Social Sciences"
    if code == "HB1-3840": return "Economic theory. Demography"
    return None

#####################################################################
# Source objects to be used for testing
#####################################################################

APPLICATION_SOURCE = {
    "id" : "abcdefghijk",
    "created_date" : "2000-01-01T00:00:00Z",
    "bibjson" : {
        # "active" : true|false,
        "title" : "The Title",
        "alternative_title" : "Alternative Title",
        "identifier": [
            {"type" : "pissn", "id" : "1234-5678"},
            {"type" : "eissn", "id" : "9876-5432"},
        ],
        "keywords" : ["word", "key"],
        "language" : ["EN", "FR"],
        "country" : "US",
        "publisher" : "The Publisher",
        "provider" : "Platform Host Aggregator",
        "institution" : "Society Institution",
        "replaces" : ["1111-1111"],
        "is_replaced_by" : ["2222-2222"],
        "discontinued_date" : "2001-01-01",
        "link": [
            {"type" : "homepage", "url" : "http://journal.url"},
            {"type" : "waiver_policy", "url" : "http://waiver.policy"},
            {"type" : "editorial_board", "url" : "http://editorial.board"},
            {"type" : "aims_scope", "url" : "http://aims.scope"},
            {"type" : "author_instructions", "url" : "http://author.instructions"},
            {"type" : "oa_statement", "url" : "http://oa.statement"}
        ],
        "subject" : [
            {"scheme" : "LCC", "term" : "Economic theory. Demography", "code" : "HB1-3840"},
            {"scheme" : "LCC", "term" : "Social Sciences", "code" : "H"}
        ],

        "oa_start" : {
            "year" : 1980,
        },
        "apc" : {
            "currency" : "GBP",
            "average_price" : 2
        },
        "submission_charges" : {
            "currency" : "USD",
            "average_price" : 4
        },
        "archiving_policy": {
            "known" : ["LOCKSS", "CLOCKSS"],
            "other" : "A safe place",
            "nat_lib" : "Trinity",
            "url": "http://digital.archiving.policy"
        },
        "editorial_review" : {
            "process" : "Open peer review",
            "url" : "http://review.process"
        },
        "plagiarism_detection" : {
            "detection": True,
            "url" : "http://plagiarism.screening"
        },
        "article_statistics" : {
            "statistics" : True,
            "url" : "http://download.stats"
        },
        "deposit_policy" : ["Sherpa/Romeo", "Store it"],
        "author_copyright" : {
            "copyright" : "True",
            "url" : "http://copyright"
        },
        "author_publishing_rights" : {
            "publishing_rights" : "True",
            "url" : "http://publishing.rights"
        },
        "allows_fulltext_indexing" : True,
        "persistent_identifier_scheme" : ["DOI", "ARK", "PURL"],
        "format" : ["HTML", "XML", "Wordperfect"],
        "publication_time" : 8,
        "license" : [
            {
                "title" : "CC MY",
                "type" : "CC MY",
                "url" : "http://licence.url",
                "open_access": True,
                "BY": True,
                "NC": True,
                "ND": False,
                "SA": False,
                "embedded" : True,
                "embedded_example_url" : "http://licence.embedded"
            }
        ]
    },
    "suggestion" : {
        "suggested_on": "2014-04-09T20:43:18Z",
        "suggester": {
            "name": "Suggester Name",
            "email": "suggester@email.com"
        },
        "articles_last_year" : {
            "count" : 16,
            "url" : "http://articles.last.year"
        },
        "article_metadata" : True
    },
    "admin" : {
        "application_status" : "pending",
        "notes" : [
            {"note" : "First Note", "date" : "2014-05-21T14:02:45Z"},
            {"note" : "Second Note", "date" : "2014-05-22T00:00:00Z"}
        ],
        "contact" : [
            {
                "email" : "contact@email.com",
                "name" : "Contact Name"
            }
        ],
        "owner" : "Owner",
        "editor_group" : "editorgroup",
        "editor" : "associate",
    }
}

######################################################################
# Complete, populated, form components
######################################################################

JOURNAL_INFO = {
    "title" : "The Title",
    "url" : "http://journal.url",
    "alternative_title" : "Alternative Title",
    "pissn" : "1234-5678",
    "eissn" : "9876-5432",
    "publisher" : "The Publisher",
    "society_institution" : "Society Institution",
    "platform" : "Platform Host Aggregator",
    "contact_name" : "Contact Name",
    "contact_email" : "contact@email.com",
    "confirm_contact_email" : "contact@email.com",
    "country" : "US",
    "processing_charges" : "True",
    "processing_charges_url" : "http://apc.com",
    "processing_charges_amount" : 2,
    "processing_charges_currency" : "GBP",
    "submission_charges" : "True",
    "submission_charges_url" : "http://submission.com",
    "submission_charges_amount" : 4,
    "submission_charges_currency" : "USD",
    "waiver_policy" : "True",
    "waiver_policy_url" : "http://waiver.policy",
    "digital_archiving_policy" : ["LOCKSS", "CLOCKSS", "A national library", "Other"],
    "digital_archiving_policy_other" : "A safe place",
    "digital_archiving_policy_library" : "Trinity",
    "digital_archiving_policy_url" : "http://digital.archiving.policy",
    "crawl_permission" : "True",
    "article_identifiers" : ["DOI", "ARK", "Other"],
    "article_identifiers_other" : "PURL",
    "download_statistics" : "True",
    "download_statistics_url" : "http://download.stats",
    "first_fulltext_oa_year" : 1980,
    "fulltext_format" : ["HTML", "XML", "Other"],
    "fulltext_format_other" : "Wordperfect",
    "keywords" : ["word", "key"],
    "languages" : ["EN", "FR"],
    "editorial_board_url" : "http://editorial.board",
    "review_process" : "Open peer review",
    "review_process_url" : "http://review.process",
    "aims_scope_url" : "http://aims.scope",
    "instructions_authors_url" : "http://author.instructions.com",
    "plagiarism_screening" : "True",
    "plagiarism_screening_url" : "http://plagiarism.screening",
    "publication_time" : 8,
    "oa_statement_url" : "http://oa.statement",
    "license_embedded" : "True",
    "license_embedded_url" : "http://licence.embedded",
    "license" : "Other",
    "license_other" : "CC MY",
    "license_checkbox" : ["BY", "NC"],
    "license_url" : "http://licence.url",
    "open_access" : "True",
    "deposit_policy" : ["Sherpa/Romeo", "Other"],
    "deposit_policy_other" : "Store it",
    "copyright" : "True",
    "copyright_url" : "http://copyright.com",
    "publishing_rights" : "True",
    "publishing_rights_url" : "http://publishing.rights",
    "replaces" : ["1111-1111"],
    "is_replaced_by" : ["2222-2222"],
    "discontinued_date" : "2001-01-01"
}

SUGGESTION = {
    "articles_last_year" : 16,
    "articles_last_year_url" : "http://articles.last.year",
    "metadata_provision" : "True"
}

SUGGESTER = {
    "suggester_name" : "Suggester",
    "suggester_email" : "suggester@email.com",
    "suggester_email_confirm" : "suggester@email.com"
}

NOTES = {
    'notes': [
        {'date': '2014-05-21T14:02:45Z', 'note': 'First Note'},
        {'date': '2014-05-22T00:00:00Z', 'note': 'Second Note'}
    ]
}

SUBJECT = {
    "subject" : ['HB1-3840', 'H']
}

JOURNAL_LEGACY = {
    "author_pays" : "Y",
    "author_pays_url" : "http://author.pays",
    "oa_end_year" : 1991
}

OWNER = {
    "owner" : "Owner"
}

EDITORIAL = {
    "editor_group" : "editorgroup",
    "editor" : "associate"
}

WORKFLOW = {
    "application_status" : "pending"
}

APPLICATION_FORMINFO = deepcopy(JOURNAL_INFO)
APPLICATION_FORMINFO.update(deepcopy(SUGGESTION))
APPLICATION_FORMINFO.update(EDITORIAL)
APPLICATION_FORMINFO.update(WORKFLOW)
APPLICATION_FORMINFO.update(SUBJECT)
APPLICATION_FORMINFO.update(SUGGESTER)
APPLICATION_FORMINFO.update(NOTES)

APPLICATION_FORM = deepcopy(APPLICATION_FORMINFO)
APPLICATION_FORM["keywords"] = ",".join(APPLICATION_FORM["keywords"])

notes = APPLICATION_FORM["notes"]
del APPLICATION_FORM["notes"]
i = 0
for n in notes:
    notekey = "notes-" + str(i) + "-note"
    datekey = "notes-" + str(i) + "-date"
    APPLICATION_FORM[notekey] = n.get("note")
    APPLICATION_FORM[datekey] = n.get("date")
    i += 1

del APPLICATION_FORM["editor_group"]

######################################################
# Main test class
######################################################

class TestEditorAppReview(DoajTestCase):

    def setUp(self):
        super(TestEditorAppReview, self).setUp()

        self.editor_group_pull = models.EditorGroup.pull_by_key
        models.EditorGroup.pull_by_key = editor_group_pull

        self.old_lcc_choices = lcc.lcc_choices
        lcc.lcc_choices = mock_lcc_choices

        self.old_lookup_code = lcc.lookup_code
        lcc.lookup_code = mock_lookup_code

    def tearDown(self):
        super(TestEditorAppReview, self).tearDown()

        models.EditorGroup.pull_by_key = self.editor_group_pull
        lcc.lcc_choices = self.old_lcc_choices

        lcc.lookup_code = self.old_lookup_code


    ###########################################################
    # Tests on the editor's reapplication form
    ###########################################################

    def test_01_editor_review_success(self):
        """Give the editor's reapplication form a full workout"""
        acc = models.Account()
        acc.set_id("richard")
        acc.add_role("editor")
        ctx = self._make_and_push_test_context(acc=acc)

        # we start by constructing it from source
        fc = formcontext.ApplicationFormFactory.get_form_context(role="editor", source=models.Suggestion(**APPLICATION_SOURCE))
        assert isinstance(fc, formcontext.EditorApplicationReview)
        assert fc.form is not None
        assert fc.source is not None
        assert fc.form_data is None
        assert fc.template is not None

        # check that we can render the form
        # FIXME: we can't easily render the template - need to look into Flask-Testing for this
        # html = fc.render_template(edit_suggestion=True)
        html = fc.render_field_group("editorial") # we know all these disabled fields are in the editorial section
        assert html is not None
        assert html != ""

        # check that the fields that should be disabled are disabled
        # "editor_group"
        rx_template = '(<input [^>]*?disabled[^>]+?name="{field}"[^>]*?>)'
        eg_rx = rx_template.replace("{field}", "editor_group")

        assert re.search(eg_rx, html)

        # now construct it from form data (with a known source)
        fc = formcontext.ApplicationFormFactory.get_form_context(
            role="editor",
            form_data=MultiDict(APPLICATION_FORM) ,
            source=models.Suggestion(**APPLICATION_SOURCE))

        assert isinstance(fc, formcontext.EditorApplicationReview)
        assert fc.form is not None
        assert fc.source is not None
        assert fc.form_data is not None

        # test each of the workflow components individually ...

        # pre-validate and ensure that the disabled fields get re-set
        fc.pre_validate()
        assert fc.form.editor_group.data == "editorgroup"

        # run the validation itself
        fc.form.subject.choices = mock_lcc_choices # set the choices allowed for the subject manually (part of the test)
        assert fc.validate(), fc.form.errors

        # run the crosswalk (no need to look in detail, xwalks are tested elsewhere)
        fc.form2target()
        assert fc.target is not None

        # patch the target with data from the source
        fc.patch_target()
        assert fc.target.created_date == "2000-01-01T00:00:00Z"
        assert fc.target.id == "abcdefghijk"
        assert len(fc.target.notes) == 2
        assert fc.target.owner == "Owner"
        assert fc.target.editor_group == "editorgroup"
        assert fc.target.editor == "associate"
        assert fc.target.application_status == "pending", fc.target.application_status # is updated by the form
        assert fc.target.bibjson().replaces == ["1111-1111"]
        assert fc.target.bibjson().is_replaced_by == ["2222-2222"]
        assert fc.target.bibjson().discontinued_date == "2001-01-01"

        # now do finalise (which will also re-run all of the steps above)
        fc.finalise()

        time.sleep(2)

        # now check that a provenance record was recorded
        prov = models.Provenance.get_latest_by_resource_id(fc.target.id)
        assert prov is not None

        ctx.pop()

    def test_02_classification_required(self):
        # Check we can mark an application 'ready' with a subject classification present
        in_progress_application = models.Suggestion(**ApplicationFixtureFactory.make_application_source())
        in_progress_application.set_application_status("in progress")

        fc = formcontext.ApplicationFormFactory.get_form_context(role='editor', source=in_progress_application)

        # Make changes to the application status via the form, check it validates
        fc.form.application_status.data = "ready"

        assert fc.validate()

        # Without a subject classification, we should not be able to set the status to 'ready'
        no_class_application = models.Suggestion(**ApplicationFixtureFactory.make_application_source())
        del no_class_application.data['bibjson']['subject']
        fc = formcontext.ApplicationFormFactory.get_form_context(role='editor', source=no_class_application)
        # Make changes to the application status via the form
        assert fc.source.bibjson().subjects() == []
        fc.form.application_status.data = "ready"

        assert not fc.validate()

        # However, we should be able to set it to a different status rather than 'ready'
        fc.form.application_status.data = "pending"

        assert fc.validate()

    def test_03_editor_review_ready(self):
        """Give the editor's reapplication form a full workout"""
        acc = models.Account()
        acc.set_id("contextuser")
        acc.add_role("editor")
        ctx = self._make_and_push_test_context(acc=acc)

        eg = models.EditorGroup()
        eg.set_name(APPLICATION_SOURCE["admin"]["editor_group"])
        eg.set_editor("contextuser")
        eg.save()

        time.sleep(2)

        # construct a context from a form submission
        source = deepcopy(APPLICATION_FORM)
        source["application_status"] = "ready"
        fd = MultiDict(source)
        fc = formcontext.ApplicationFormFactory.get_form_context(
            role="editor",
            form_data=fd,
            source=models.Suggestion(**APPLICATION_SOURCE))

        fc.finalise()
        time.sleep(2)

        # now check that a provenance record was recorded
        count = 0
        for prov in models.Provenance.iterall():
            if prov.action == "edit":
                count += 1
            if prov.action == "status:ready":
                count += 10
        assert count == 11

        ctx.pop()

    def test_04_editor_review_disallowed_statuses(self):
        """ Check that editors can't access applications beyond their review process """

        acc = models.Account()
        acc.set_id("contextuser")
        acc.add_role("editor")
        ctx = self._make_and_push_test_context(acc=acc)

        # Check that an accepted application can't be regressed by an editor
        accepted_source = APPLICATION_SOURCE.copy()
        accepted_source['admin']['application_status'] = 'accepted'

        ready_form = APPLICATION_FORM.copy()
        ready_form['application_status'] = 'ready'

        # Construct the formcontext from form data (with a known source)
        fc = formcontext.ApplicationFormFactory.get_form_context(
            role="editor",
            form_data=MultiDict(ready_form),
            source=models.Suggestion(**accepted_source)
        )

        assert isinstance(fc, formcontext.EditorApplicationReview)
        assert fc.form is not None
        assert fc.source is not None
        assert fc.form_data is not None

        # Finalise the formcontext. This should raise an exception because the application has already been accepted.
        assert_raises(formcontext.FormContextException, fc.finalise)

        # Check that an application status can't be edited by editors when on hold,
        # since this status must have been set by a managing editor.
        held_source = APPLICATION_SOURCE.copy()
        held_source['admin']['application_status'] = 'on hold'

        progressing_form = APPLICATION_FORM.copy()
        progressing_form['application_status'] = 'in progress'

        # Construct the formcontext from form data (with a known source)
        fc = formcontext.ApplicationFormFactory.get_form_context(
            role="editor",
            form_data=MultiDict(progressing_form),
            source=models.Suggestion(**held_source)
        )

        assert isinstance(fc, formcontext.EditorApplicationReview)
        assert fc.form is not None
        assert fc.source is not None
        assert fc.form_data is not None

        # Finalise the formcontext. This should raise an exception because the application status is out of bounds.
        assert_raises(formcontext.FormContextException, fc.finalise)

        # Check that an application status can't be brought backwards in the review process
        pending_source = APPLICATION_SOURCE.copy()

        progressing_form = APPLICATION_FORM.copy()
        progressing_form['application_status'] = 'in progress'

        # Construct the formcontext from form data (with a known source)
        fc = formcontext.ApplicationFormFactory.get_form_context(
            role="associate_editor",
            form_data=MultiDict(progressing_form),
            source=models.Suggestion(**pending_source)
        )

        # Finalise the formcontext. This should raise an exception because the application status can't go backwards.
        assert_raises(formcontext.FormContextException, fc.finalise)

        ctx.pop()
