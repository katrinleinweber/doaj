from portality import models
from datetime import datetime as dt
from portality import reapplication
from portality.core import app
import os
import codecs
from portality.clcsv import UnicodeWriter


def delete_existing_reapp():
    """Note that this cannot be run in isolation, because it leaves behind unresolved current_application fields in journals"""

    # delete all the suggestions
    q = models.SuggestionQuery(statuses=['reapplication', 'submitted']).query()
    models.Suggestion.delete_by_query(query=q)

    # remove all of the current reapplication records
    models.BulkReApplication.delete_all()


def create_reapplications():
    all_journals = models.Journal.all_in_doaj()
    start_date = app.config.get("TICK_THRESHOLD", "2014-03-19T00:00:00Z")
    date_format = "%Y-%m-%dT%H:%M:%SZ"

    for_reapplication = []

    for j in all_journals:
        d1 = dt.strptime(j.created_date, date_format)
        d2 = dt.strptime(start_date, date_format)
        if d1 < d2:
            for_reapplication.append(j)

    for r in for_reapplication:
        r.make_reapplication()


def make_bulk_reapp_csv():
    acc = models.Account.all()
    failed_bulk_reapps = []
    email_list_10_plus = []
    email_list_less_10 = []
    for a in acc:
        q = models.SuggestionQuery(owner=a.id).query()
        suggestions = models.Suggestion.q2obj(q=q, size=30000)
        contact = []
        if len(suggestions) >= 11:
            contact.append(a.id)
            contact.append(a.email)
            email_list_10_plus.append(contact)
            filename = a.id + ".csv"
            filepath = os.path.join(app.config.get("BULK_REAPP_PATH"), filename)

            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                except IOError as e:
                    failed_bulk_reapps.append({a.id: e.message})

            reapplication.make_csv(filepath, suggestions)

            bulk_reapp = models.BulkReApplication()
            bulk_reapp.set_spreadsheet_name(filename)
            bulk_reapp.set_owner(a.id)
            bulk_reapp.save()
        elif len(suggestions) > 0:  # only add to the email list if they actually have suggestions at all
            contact.append(a.id)
            contact.append(a.email)
            email_list_less_10.append(contact)

    with codecs.open('email_list_11_plus.csv', 'wb', encoding='utf-8') as csvfile:
        wr_writer = UnicodeWriter(csvfile)
        wr_writer.writerows(email_list_10_plus)

    with codecs.open('email_list_less_11.csv', 'wb', encoding='utf-8') as csvfile:
        wr_writer = UnicodeWriter(csvfile)
        wr_writer.writerows(email_list_less_10)

    if failed_bulk_reapps:
        print "Failed bulk reapplications"
        print failed_bulk_reapps

# FIXME: this is going to do /all/ rejected applications, not just the ones that were
# rejected by the reject script
def emails_rejected():
    email_list = []
    q = models.SuggestionQuery(statuses=['rejected']).query()
    rejected = models.Suggestion.q2obj(q=q, size=30000)
    for r in rejected:
        contact = []
        contact.append(r.get_latest_contact_name())
        contact.append(r.get_latest_contact_email())
        contact.append(r.bibjson().title)
        email_list.append(contact)

    with codecs.open('emails_rejected.csv', 'wb', encoding='utf-8') as csvfile:
        wr_writer = UnicodeWriter(csvfile)
        wr_writer.writerows(email_list)


def main():
    delete_existing_reapp()
    create_reapplications()
    make_bulk_reapp_csv()
    emails_rejected()

if __name__ == "__main__":
    main()






