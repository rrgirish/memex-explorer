from __future__ import absolute_import

import subprocess
import os
import shlex
import time
import shutil
import sys
from celery import shared_task, Task

from django.db import IntegrityError

from task_manager.models import CeleryTask

from apps.crawl_space.settings import LANG_DETECT_PATH, CCA_PATH
from apps.crawl_space.models import Crawl

import nutch as nutch_rest_api

# TODO - pull out this hardcode search
if os.path.exists('/home/vagrant/miniconda/envs/memex/bin/nutch'):
    nutch_path = '/home/vagrant/miniconda/envs/memex/lib/nutch/bin/nutch'
    crawl_path = '/home/vagrant/miniconda/envs/memex/lib/nutch/bin/crawl'
    ache_path = '/home/vagrant/miniconda/envs/memex/bin/ache'
else:
    nutch_path = 'nutch'
    crawl_path = 'crawl'
    ache_path = 'ache'
# END TODO

# TODO - provide Nutch Common Crawl dump when added to REST API

class NutchTask(Task):
    abstract = True

@shared_task(bind=True, base=NutchTask)
def nutch(self, crawl, rounds=1, *args, **kwargs):
    self.crawl = crawl
    nutch_client = nutch_rest_api.Nutch()
    seed_client = nutch_client.Seeds()

    # TODO: Remove this Shim when https://github.com/memex-explorer/memex-explorer/pull/682 lands
    seed_urls = open(self.crawl.seeds_list.path).readlines()
    # END SHIM
    seed = seed_client.create('wikipedia_seed', seed_urls)

    rest_crawl = nutch_client.Crawl(seed, rounds=self.crawl.rounds_left)

    self.crawl_task = CeleryTask(pid=0, crawl=self.crawl, uuid=self.request.id)
    self.crawl_task.save()
    # Check whether a CeleryTask already exists. If no, create the new object. If
    # yes (IntegrityError), update the rows of the already existing object.

    # TODO: rip this out
    from apps.crawl_space.viz.url_trails import load_data
    import numpy as np
    from datetime import timedelta

    x, x0, urls = load_data()
    min_x = min(x0)
    max_x = max(x[:5])

    second_delta = np.timedelta64(timedelta(seconds=1))


    def progress_crawl(min_x, max_x):
        from bokeh.session import Session
        from bokeh.document import Document
        from bokeh.models import ColumnDataSource
        from bokeh.models.glyphs import Segment, Circle


        session = Session()
        session.use_doc("wiki_crawl")
        document = Document()
        session.load_document(document)


        min_x += second_delta
        max_x += second_delta

        if len(document.context.children) == 0:
            sys.stderr.write("no wiki_crawl document\n")
            return min_x, max_x

        p1 = document.context.children[0]


        active_min = x0.searchsorted(min_x)
        active_max = x.searchsorted(max_x, side='right')

        active_x = x[active_min:active_max]
        active_x0 = x0[active_min:active_max]
        active_urls = urls[active_min:active_max]

        p1.y_range.factors = active_urls

        # see https://github.com/bokeh/bokeh/issues/1056
        p1.x_range.start = min_x
        p1.x_range.end = max_x

        # TODO: Find out why this is necessary
        source3 = ColumnDataSource(dict(
            x=active_x,
            x0=active_x0,
            urls=active_urls,
            )
        )

        p1.renderers = p1.renderers[:-2]
        glyph1 = Segment(x0="x0", y0="urls", x1="x", y1="urls", line_color="orange", line_width=10)
        p1.add_glyph(source3, glyph1)
        glyph2 = Circle(x="x", y="urls", size=5, fill_color="green", line_color="orange", line_width=12)
        p1.add_glyph(source3, glyph2)
        # END TODO

        session.store_document(document)
        return min_x, max_x
    # END TODO rip

    while self.crawl.rounds_left:
        if rest_crawl.currentJob is None:
            rest_crawl.currentJob = rest_crawl.jobClient.create('GENERATE')

        active_job = rest_crawl.progress(nextRound=False)
        while active_job:
            time.sleep(1)
            # TODO: replace with non-fake crawl viz
            old_job = active_job
            active_job = rest_crawl.progress(nextRound=False)
            min_x, max_x = progress_crawl(min_x, max_x)
            if active_job and active_job != old_job:
                self.crawl.status = active_job.info()['type']
                self.crawl.save()
                # TODO: update pages crawled here from crawldb when appropriate
        self.crawl.rounds_left -= 1
        self.crawl.save()
    self.crawl_task = None
    self.crawl.status = 'FINISHED'
    self.crawl.save()



def ache_log_statistics(crawl):
    harvest_path = os.path.join(crawl.get_crawl_path(), 'data_monitor/harvestinfo.csv')
    proc = subprocess.Popen(["tail", "-n", "1", harvest_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if stderr and b"No such file or directory" not in stderr:
        raise AcheException(stderr)

    harvest_stats = stdout.decode()

    if not harvest_stats:
        return

    relevant, crawled = tuple(harvest_stats.split('\t')[:2])
    crawl.harvest_rate = "%.2f" % (float(relevant) / float(crawled))
    crawl.pages_crawled = crawled
    crawl.save()


@shared_task(bind=True)
def ache(self, crawl, *args, **kwargs):
    self.crawl = crawl
    call = [
        ache_path,
        "startCrawl",
        "-o",
        self.crawl.get_crawl_path(),
        "-c",
        self.crawl.get_config_path(),
        "-s",
        self.crawl.seeds_list.path,
        "-m",
        self.crawl.crawl_model.get_model_path(),
        "-e",
        self.crawl.index_name,
    ]
    with open(os.path.join(self.crawl.get_crawl_path(), 'crawl_proc.log'), 'a') as stdout:
        proc = subprocess.Popen(call, stdout=stdout, stderr=subprocess.PIPE,
            preexec_fn=os.setsid)

    # Check whether a CeleryTask already exists. If no, create the new object. If
    # yes (IntegrityError), update the rows of the already existing object.
    try:
        self.crawl_task = CeleryTask(pid=proc.pid, crawl=self.crawl, uuid=self.request.id)
        self.crawl_task.save()
    except IntegrityError:
        self.crawl_task = CeleryTask.objects.get(crawl=self.crawl)
        self.crawl_task.pid = proc.pid
        self.crawl_task.uuid = self.request.id
        self.crawl_task.save()
    stdout, stderr = proc.communicate()
    if proc.returncode > 0:
        raise RuntimeError("Crawl has failed. Please review the crawl logs.")
    return "Stopped"
