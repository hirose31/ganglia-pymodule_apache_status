#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import threading
import time
import urllib2

descriptors = list()
Desc_Skel   = {}
Scoreboard  = {
    'ap_waiting'         : { 'key': '_', 'desc': 'Waiting for Connection' },
    'ap_starting'        : { 'key': 'S', 'desc': 'Starting up' },
    'ap_reading_request' : { 'key': 'R', 'desc': 'Reading Request' },
    'ap_sending_reply'   : { 'key': 'W', 'desc': 'Sending Reply' },
    'ap_keepalive'       : { 'key': 'K', 'desc': 'Keepalive (read)' },
    'ap_dns_lookup'      : { 'key': 'D', 'desc': 'DNS Lookup' },
    'ap_closing'         : { 'key': 'C', 'desc': 'Closing connection' },
    'ap_logging'         : { 'key': 'L', 'desc': 'Logging' },
    'ap_gracefully_fin'  : { 'key': 'G', 'desc': 'Gracefully finishing' },
    'ap_idle'            : { 'key': 'I', 'desc': 'Idle cleanup of worker' },
    'ap_open_slot'       : { 'key': '.', 'desc': 'Open slot with no current process' },
    }
Scoreboard_bykey = dict([(v["key"],k) for (k,v) in Scoreboard.iteritems()])

_Worker_Thread = None
_Lock = threading.Lock() # synchronization lock

class UpdateApacheStatusThread(threading.Thread):
    '''update Apache status'''

    def __init__(self, params):
        threading.Thread.__init__(self)
        self.running          = False
        self.shuttingdown     = False
        self.url              = params["url"]
        self.virtual_host     = ""
        if "virtual_host" in params:
            self.virtual_host = params["virtual_host"]
        self.refresh_rate     = int(params["refresh_rate"])
        self.status           = {}

    def shutdown(self):
        self.shuttingdown = True
        if not self.running:
            return
        self.join()

    def run(self):
        self.running = True

        while not self.shuttingdown:
            _Lock.acquire()
            self.update_status()
            _Lock.release()

            time.sleep(self.refresh_rate)

        self.running = False

    def update_status(self):
        req = urllib2.Request(url = self.url)
        if self.virtual_host:
            req.add_header('Host', self.virtual_host)
        res = urllib2.urlopen(req)

        self.status = dict( [(k, 0) for k in Scoreboard.keys()] ) # initialize
        for l in res:
            l = l.rstrip()
            if l.find("Scoreboard:") == 0:
                scline = l.split(": ", 1)[1].rstrip()
                for sck in scline:
                    self.status[ Scoreboard_bykey[sck] ] += 1
            elif l.find("ReqPerSec:") == 0:
                scline = l.split(": ", 1)[1].rstrip()
                self.status["ap_rps"] = float(scline)
        res.close()

    def status_of(self, name):
        val = 0
        if name in self.status:
            _Lock.acquire()
            val = self.status[name]
            _Lock.release()
        return val

def create_desc(prop):
    d = Desc_Skel.copy()
    for k,v in prop.iteritems():
        d[k] = v
    return d

def process_status_of(name):
    return _Worker_Thread.status_of(name)

def metric_init(params):
    global descriptors, Desc_Skel, _Worker_Thread

    print '[apache_status] Received the following parameters'
    print params

    Desc_Skel = {
        'name'        : 'XXX',
        'call_back'   : process_status_of,
        'time_max'    : 60,
        'value_type'  : 'uint',
        'units'       : 'proc',
        'slope'       : 'both',
        'format'      : '%d',
        'description' : 'XXX',
        'groups'      : 'apache',
        }

    if "refresh_rate" not in params:
        params["refresh_rate"] = 10
    if "url" not in params:
        params["url"] = "http://localhost/server-status?auto"

    _Worker_Thread = UpdateApacheStatusThread(params)
    _Worker_Thread.start()

    # IP:HOSTNAME
    if "spoof_host" in params:
        Desc_Skel["spoof_host"] = params["spoof_host"]

    descriptors.append(create_desc({
                "name"       : "ap_rps",
                "value_type" : "float",
                "units"      : "req/sec",
                "format"     : "%.3f",
                "description": "request per second",
                }))

    for k,v in Scoreboard.iteritems():
        descriptors.append(create_desc({
                    "name"        : k,
                    "description" : v["desc"],
                    }))

    return descriptors

def metric_cleanup():
    '''Clean up the metric module.'''
    _Worker_Thread.shutdown()

if __name__ == '__main__':
    try:
        params = {
            'url'         : 'http://localhost/server-status?auto',
            #'virtual_host': 'health',
            }
        metric_init(params)
        while True:
            for d in descriptors:
                v = d['call_back'](d['name'])
                if d['name'] == "ap_rps":
                    print 'value for %s is %.3f' % (d['name'], v)
                else:
                    print 'value for %s is %u'   % (d['name'], v)
            time.sleep(5)
    except KeyboardInterrupt:
        time.sleep(0.2)
        os._exit(1)
