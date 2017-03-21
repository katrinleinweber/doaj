from flask_login import current_user
from portality import models, article
from portality.core import app

from portality.tasks.redis_huey import main_queue, configure
from portality.decorators import write_required

from portality.background import BackgroundTask, BackgroundApi, BackgroundException, RetryException
import ftplib, os, requests, traceback
from urlparse import urlparse

DEFAULT_MAX_REMOTE_SIZE=262144000
CHUNK_SIZE=1048576

def ftp_upload(job, path, parsed_url, file_upload):
    # 1. find out the file size
    #    (in the meantime the size command will return an error if
    #     the file does not exist)
    # 2. if not too big, download it
    size_limit = app.config.get("MAX_REMOTE_SIZE", DEFAULT_MAX_REMOTE_SIZE)

    too_large = [False]  # you CANNOT override (rebind) vars inside nested funcs in python 2
                         # and we can't pass too_large and downloaded as args to
                         # ftp_callback either since we don't control what args it gets
                         # hence, widely adopted ugly hack - since you can READ nonlocal
                         # vars from nested funcs, we use a mutable container!
    downloaded = [0]
    def ftp_callback(chunk):
        '''Callback for processing downloaded chunks of the FTP file'''
        if too_large[0]:
            return

        downloaded[0] += len(bytes(chunk))
        if downloaded[0] > size_limit:
            too_large[0] = True
            return

        if chunk:
            with open(path, 'ab') as o:
                o.write(chunk)
                o.flush()


    try:
        f = ftplib.FTP(parsed_url.hostname, parsed_url.username, parsed_url.password)

        r = f.sendcmd('TYPE I')  # SIZE is not usually allowed in ASCII mode, so set to binary mode
        if not r.startswith('2'):
            job.add_audit_message('could not set binary mode in target FTP server while checking file exists')
            file_upload.failed("Unable to download file from FTP site")
            return False

        file_size = f.size(parsed_url.path)
        if file_size < 0:
            # this will either raise an error which will get caught below
            # or, very rarely, will return an invalid size
            job.add_audit_message('invalid file size: ' + str(file_size))
            file_upload.failed("Unable to download file from FTP site")
            return False

        if file_size > size_limit:
            file_upload.failed("The file at the URL was too large")
            job.add_audit_message("too large")
            return False

        f.close()

        f = ftplib.FTP(parsed_url.hostname, parsed_url.username, parsed_url.password)
        c = f.retrbinary('RETR ' + parsed_url.path, ftp_callback, CHUNK_SIZE)
        if too_large[0]:
            file_upload.failed("The file at the URL was too large")
            job.add_audit_message("too large")
            try:
                os.remove(path)
            except:
                pass
            return False

        if c.startswith('226'):
            file_upload.downloaded()
            return True

        msg = u'Bad code returned by FTP server for the file transfer: "{0}"'.format(c)
        job.add_audit_message(msg)
        file_upload.failed(msg)
        return False

    except Exception as e:
        job.add_audit_message('error during FTP file download: ' + str(e.args))
        file_upload.failed("Unable to download file from FTP site")
        return False


def http_upload(job, path, file_upload):
    try:
        r = requests.get(file_upload.filename, stream=True)
        if r.status_code != requests.codes.ok:
            job.add_audit_message("The URL could not be accessed")
            file_upload.failed("The URL could not be accessed")
            return False

        # check the content length
        size_limit = app.config.get("MAX_REMOTE_SIZE", DEFAULT_MAX_REMOTE_SIZE)
        cl = r.headers.get("content-length")
        try:
            cl = int(cl)
        except:
            cl = 0

        if cl > size_limit:
            file_upload.failed("The file at the URL was too large")
            job.add_audit_message("too large")
            return False

        too_large = False
        with open(path, 'wb') as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE): # 1Mb chunks
                downloaded += len(bytes(chunk))
                # check the size limit again
                if downloaded > size_limit:
                    file_upload.failed("The file at the URL was too large")
                    job.add_audit_message("too large")
                    too_large = True
                    break
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
    except:
        job.add_audit_message("The URL could not be accessed")
        file_upload.failed("The URL could not be accessed")
        return False

    if too_large:
        try:
            os.remove(path)
        except:
            pass
        return False

    file_upload.downloaded()
    return True

class IngestArticlesBackgroundTask(BackgroundTask):

    __action__ = "ingest_articles"

    def run(self):
        """
        Execute the task as specified by the background_jon
        :return:
        """
        job = self.background_job
        params = job.params

        if params is None:
            raise BackgroundException(u"IngestArticleBackgroundTask.run run without sufficient parameters")

        file_upload_id = self.get_param(params, "file_upload_id")
        if file_upload_id is None:
            raise BackgroundException(u"IngestArticleBackgroundTask.run run without sufficient parameters")

        file_upload = models.FileUpload.pull(file_upload_id)
        if file_upload is None:
            raise BackgroundException(u"IngestArticleBackgroundTask.run unable to find file upload with id {x}".format(x=file_upload_id))

        try:
            # if the file "exists", this means its a remote file that needs to be downloaded, so do that
            if file_upload.status == "exists":
                job.add_audit_message(u"Downloading file for file upload {x}, job {y}".format(x=file_upload_id, y=job.id))
                self._download(file_upload)

            # if the file is validated, which will happen if it has been uploaded, or downloaded successfully, process it.
            if file_upload.status == "validated":
                job.add_audit_message(u"Importing file for file upload {x}, job {y}".format(x=file_upload_id, y=job.id))
                self._process(file_upload)
        finally:
            file_upload.save()

    def _download(self, file_upload):
        job = self.background_job
        upload_dir = app.config.get("UPLOAD_DIR")
        path = os.path.join(upload_dir, file_upload.local_filename)

        # first, determine if ftp or http
        parsed_url = urlparse(file_upload.filename)
        if parsed_url.scheme == 'ftp':
            if not ftp_upload(job, path, parsed_url, file_upload):
                return False
        elif parsed_url.scheme in ['http', "https"]:
            if not http_upload(job, path, file_upload):
                return False
        else:
            msg = u"We only support HTTP(s) and FTP uploads by URL. This is a: {x}".format(x=parsed_url.scheme)
            job.add_audit_message(msg)
            file_upload.failed(msg)
            return False

        job.add_audit_message(u"Downloaded {x} as {y}".format(x=file_upload.filename, y=file_upload.local_filename))

        # now we have the record in the index and on disk, we can attempt to
        # validate it
        try:
            with open(path) as handle:
                actual_schema = article.check_schema(handle, file_upload.schema)
        except:
            # file is a dud, so remove it
            try:
                os.remove(path)
            except:
                job.add_audit_message(u"Error cleaning up invalid file: {x}".format(x=traceback.format_exc()))
            file_upload.failed("Unable to parse file")
            raise

        # if we get to here then we have a successfully downloaded and validated
        # document, so we can write it to the index
        job.add_audit_message(u"Validated file as schema {x}".format(x=actual_schema))
        file_upload.validated(actual_schema)
        return True

    def _process(self, file_upload):
        job = self.background_job
        upload_dir = app.config.get("UPLOAD_DIR")
        path = os.path.join(upload_dir, file_upload.local_filename)

        if not os.path.exists(path):
            raise RetryException()

        job.add_audit_message(u"Importing from {x}".format(x=path))

        success = 0
        fail = 0
        update = 0
        new = 0

        try:
            with open(path) as handle:
                result = article.ingest_file(handle, format_name=file_upload.schema, owner=file_upload.owner, upload_id=file_upload.id)
                success = result["success"]
                fail = result["fail"]
                update = result["update"]
                new = result["new"]
        except article.IngestException as e:
            job.add_audit_message(u"IngestException: {x}".format(x=traceback.format_exc()))
            file_upload.failed(e.message)
            try:
                os.remove(path)
            except:
                job.add_audit_message(u"Error cleaning up file which caused IngestException: {x}".format(x=traceback.format_exc()))
        except Exception as e:
            job.add_audit_message(u"File system error while reading file: {x}".format(x=traceback.format_exc()))
            file_upload.failed("File system error when reading file")
            try:
                os.remove(path)
            except:
                job.add_audit_message(u"Error cleaning up file which caused Exception: {x}".format(x=traceback.format_exc()))

        if success == 0 and fail > 0:
            file_upload.failed("All articles in file failed to import")
        if success > 0 and fail == 0:
            file_upload.processed(success, update, new)
        if success > 0 and fail > 0:
            file_upload.partial(success, fail, update, new)

        try:
            os.remove(path)
        except Exception as e:
            job.add_audit_message(u"Error while deleting file {x}: {y}".format(x=path, y=e.message))

    def cleanup(self):
        """
        Cleanup after a successful OR failed run of the task
        :return:
        """
        job = self.background_job
        params = job.params

    @classmethod
    def prepare(cls, username, **kwargs):
        """
        Take an arbitrary set of keyword arguments and return an instance of a BackgroundJob,
        or fail with a suitable exception

        :param kwargs: arbitrary keyword arguments pertaining to this task type
        :return: a BackgroundJob instance representing this task
        """

        upload_dir = app.config.get("UPLOAD_DIR")
        if upload_dir is None:
            raise BackgroundException("UPLOAD_DIR is not set in configuration")

        f = kwargs.get("upload_file")
        schema = kwargs.get("schema")
        url = kwargs.get("url")
        previous = kwargs.get("previous", [])

        if f is None and url is None:
            raise BackgroundException("You must specify one of 'upload_file' or 'url' as keyword arguments")
        if schema is None:
            raise BackgroundException("You must specify 'schema' in the keyword arguments")

        file_upload_id = None
        if f is not None and f.filename != "":
            file_upload_id = cls._file_upload(username, f, schema, previous)
        elif url is not None and url != "":
            file_upload_id = cls._url_upload(username, url, schema, previous)

        if file_upload_id is None:
            raise BackgroundException("No file upload record was created")

        # first prepare a job record
        job = models.BackgroundJob()
        job.user = username
        job.action = cls.__action__

        params = {}
        cls.set_param(params, "file_upload_id", file_upload_id)
        job.params = params

        return job

    @classmethod
    def submit(cls, background_job):
        """
        Submit the specified BackgroundJob to the background queue

        :param background_job: the BackgroundJob instance
        :return:
        """
        background_job.save(blocking=True)
        ingest_articles.schedule(args=(background_job.id,), delay=10)

    @classmethod
    def _file_upload(cls, username, f, schema, previous):
        # prep a record to go into the index, to record this upload
        record = models.FileUpload()
        record.upload(username, f.filename)
        record.set_id()

        # the file path that we are going to write to
        xml = os.path.join(app.config.get("UPLOAD_DIR", "."), record.local_filename)

        # it's critical here that no errors cause files to get left behind unrecorded
        try:
            # write the incoming file out to the XML file
            f.save(xml)

            # save the index entry
            record.save()
        except:
            # if we can't record either of these things, we need to back right off
            try:
                os.remove(xml)
            except:
                pass
            try:
                record.delete()
            except:
                pass

            raise BackgroundException("Failed to upload file - please contact an administrator")

        # now we have the record in the index and on disk, we can attempt to
        # validate it
        try:
            actual_schema = None
            with open(xml) as handle:
                actual_schema = article.check_schema(handle, schema)
        except:
            # file is a dud, so remove it
            try:
                os.remove(xml)
            except:
                pass

            # if we're unable to validate the file, we should record this as
            # a file error.
            record.failed("Unable to parse file")
            record.save()
            previous.insert(0, record)
            raise BackgroundException("Failed to parse file - it is invalid XML; please fix it before attempting to upload again.")

        if actual_schema:
            record.validated(actual_schema)
            record.save()
            previous.insert(0, record)
        else:
            record.failed("File could not be validated against a known schema")
            record.save()
            os.remove(xml)
            previous.insert(0, record)
            raise BackgroundException("File could not be validated against a known schema; please fix this before attempting to upload again")

        return record.id

    @classmethod
    def _url_upload(cls, username, url, schema, previous):
        # first define a few functions
        def __http_upload(record, previous, url):
            # first thing to try is a head request, supporting redirects
            head = requests.head(url, allow_redirects=True)
            if head.status_code == requests.codes.ok:
                return __ok(record, previous)

            # if we get to here, the head request failed.  This might be because the file
            # isn't there, but it might also be that the server doesn't support HEAD (a lot
            # of webapps [including this one] don't implement it)
            #
            # so we do an interruptable get request instead, so we don't download too much
            # unnecessary content
            get = requests.get(url, stream=True)
            get.close()
            if get.status_code == requests.codes.ok:
                return __ok(record, previous)
            return __fail(record, previous, error='error while checking submitted file reference: {0}'.format(get.status_code))


        def __ftp_upload(record, previous, parsed_url):
            # 1. find out whether the file exists
            # 2. that's it, return OK

            # We might as well check if the file exists using the SIZE command.
            # If the FTP server does not support SIZE, our article ingestion
            # script is going to refuse to process the file anyway, so might as
            # well get a failure now.
            # Also it's more of a faff to check file existence using LIST commands.
            try:
                f = ftplib.FTP(parsed_url.hostname, parsed_url.username, parsed_url.password)
                r = f.sendcmd('TYPE I')  # SIZE is not usually allowed in ASCII mode, so set to binary mode
                if not r.startswith('2'):
                    return __fail(record, previous, error='could not set binary '
                        'mode in target FTP server while checking file exists')
                if f.size(parsed_url.path) < 0:
                    # this will either raise an error which will get caught below
                    # or, very rarely, will return an invalid size
                    return __fail(record, previous, error='file does not seem to exist on FTP server')

            except Exception as e:
                return __fail(record, previous, error='error during FTP file existence check: ' + str(e.args))

            return __ok(record, previous)


        def __ok(record, previous):
            record.exists()
            record.save()
            previous.insert(0, record)
            return record.id

        def __fail(record, previous, error):
            message = 'The URL could not be accessed; ' + error
            record.failed(message)
            record.save()
            previous.insert(0, record)
            raise BackgroundException(message)

        # prep a record to go into the index, to record this upload.  The filename is the url
        record = models.FileUpload()
        record.upload(username, url)
        record.set_id()
        record.set_schema(schema) # although it could be wrong, this will get checked later

        # now we attempt to verify that the file is retrievable
        try:
            # first, determine if ftp or http
            parsed_url = urlparse(url)
            if parsed_url.scheme in ['http', "https"]:
                return __http_upload(record, previous, url)
            elif parsed_url.scheme == 'ftp':
                return __ftp_upload(record, previous, parsed_url)
            else:
                return __fail(record, previous, error='unsupported URL scheme "{0}". Only HTTP(s) and FTP are supported.'.format(parsed_url.scheme))
        except BackgroundException as e:
            raise
        except Exception as e:
            return __fail(record, previous, error="please check it before submitting again; " + e.message)

@main_queue.task(**configure("ingest_articles"))
@write_required(script=True)
def ingest_articles(job_id):
    job = models.BackgroundJob.pull(job_id)
    task = IngestArticlesBackgroundTask(job)
    BackgroundApi.execute(task)