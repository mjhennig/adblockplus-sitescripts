# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import MySQLdb, hashlib, sys, os, re, marshal
from time import time
from email.utils import parseaddr
from sitescripts.utils import get_config, get_template, setupStderr
from sitescripts.reports.utils import calculateReportSecret, get_db, executeQuery
import sitescripts.subscriptions.subscriptionParser as subscriptionParser

def updateDigests(dir):
  global currentTime
  
  subs = subscriptionParser.readSubscriptions()

  subscriptions = {}
  emails = {}
  for subscription in subs.values():
    for title, url, complete in subscription.variants:
      subscriptions[url] = subscription
    name, email = parseaddr(subscription.email)
    if email != '':
      emails[email] = []

  startTime = currentTime - get_config().getint('reports', 'digestDays') * 24*60*60
  cursor = get_db().cursor(MySQLdb.cursors.DictCursor)
  executeQuery(cursor,
              '''SELECT guid, dump FROM #PFX#reports WHERE ctime >= FROM_UNIXTIME(%s)''',
              (startTime))

  for dbreport in cursor:
    reportData = marshal.loads(dbreport['dump'])

    matchSubscriptions = {}
    for filters in reportData.get('filters', []):
      for url in filters.get('subscriptions', []):
        if url in subscriptions:
          matchSubscriptions[url] = subscriptions[url]

    report = {
      'url': get_config().get('reports', 'urlRoot') + dbreport['guid'] + '#secret=' + calculateReportSecret(dbreport['guid']),
      'site': reportData.get('siteName', 'unknown'),
      'comment': re.sub(r'[\x00-\x20]', r' ', reportData.get('comment', '')),
      'type': reportData.get('type', 'unknown'),
      'subscriptions': [],
      'numSubscriptions': len(reportData.get('subscriptions', [])),
      'matchSubscriptions': matchSubscriptions.values(),
      'email': reportData.get('email', None),
      'screenshot': reportData.get('screenshot', None) != None,
      'screenshotEdited': reportData.get('screenshotEdited', False),
      'knownIssues': len(reportData.get('knownIssues', [])),
    }
    
    recipients = set()
    
    reportType = reportData.get('type', 'unknown')
    if reportType == 'false positive' or reportType == 'false negative':
      for subscription in reportData.get('subscriptions', []):
        subscriptionID = subscription.get('id', 'unknown')
        # Send false negatives to all subscription authors, false positives
        # only to subscriptions with matching filters
        if subscriptionID in subscriptions and (reportType == 'false negative' or subscriptionID in matchSubscriptions):
          name, email = parseaddr(subscriptions[subscriptionID].email)
          if email and not email in recipients:
            recipients.add(email)
            emails[email].append(report)
          report['subscriptions'].append(subscriptions[subscriptionID])

  for email, reports in emails.iteritems():
    if len(reports) == 0:
      continue
    file = getDigestFilename(dir, email)
    template = get_template(get_config().get('reports', 'htmlDigestTemplate'))
    template.stream({'email': email, 'reports': reports}).dump(file, encoding='utf-8')

def getDigestFilename(dir, email):
  hash = hashlib.md5()
  hash.update(email)
  return os.path.join(dir, hash.hexdigest() + '.html')

if __name__ == '__main__':
  setupStderr()
  currentTime = time()
  updateDigests(get_config().get('reports', 'digestPath'))
