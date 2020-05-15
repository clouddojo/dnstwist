#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from queue import Queue
from uuid import uuid4
from time import time

from flask import Flask, request, jsonify, send_from_directory

from dnstwist import UrlParser, DomainFuzz, DomainThread, THREAD_COUNT_DEFAULT


PORT = int(os.environ.get('PORT', 8000))
HOST= os.environ.get('HOST', '127.0.0.1')
THREAD_COUNT = int(os.environ.get('THREAD_COUNT', THREAD_COUNT_DEFAULT))
NAMESERVER = os.environ.get('NAMESERVER')
SESSION_TTL = int(os.environ.get('SESSION_TTL', 300))
SESSION_MAX = int(os.environ.get('SESSION_MAX', 20))
WEBAPP_HTML = 'webapp.html'
WEBAPP_DIR = os.path.dirname(__file__)


sessions = []
app = Flask(__name__)


class Session():
	def __init__(self, url, nameserver=None, thread_count=THREAD_COUNT):
		self.id = str(uuid4())
		self.timestamp = int(time())
		self.url = UrlParser(url)
		self.nameserver = nameserver
		self.thread_count = thread_count
		self.jobs = Queue()
		self.threads = []
		fuzz = DomainFuzz(self.url.domain)
		fuzz.generate()
		self.permutations = fuzz.domains

	def scan(self):
		for i in range(len(self.permutations)):
			self.jobs.put(self.permutations[i])
		for _ in range(self.thread_count):
			worker = DomainThread(self.jobs)
			worker.setDaemon(True)
			worker.option_extdns = True
			worker.option_geoip = True
			if self.nameserver:
				worker.nameservers = [self.nameserver]
			worker.start()
			self.threads.append(worker)

	def stop(self):
		self.jobs.queue.clear()
		for worker in self.threads:
			worker.stop()
			worker.join()

	def status(self):
		total = len(self.permutations)
		remaining = self.jobs.qsize()
		complete = total - remaining
		return {
			'id': self.id,
			'timestamp': self.timestamp,
			'url': self.url.full_uri(),
			'total': total,
			'complete': complete,
			'remaining': remaining
			}

	def domains(self):
		return [x for x in self.permutations if len(x) > 2]


@app.route('/')
def root():
	return send_from_directory(WEBAPP_DIR, WEBAPP_HTML)


@app.route('/api/scans', methods=['POST'])
def api_scan():
	for s in sessions:
		status = s.status()
		if status['remaining'] == 0 and (status['timestamp'] + SESSION_TTL) < time():
			sessions.remove(s)
	if len(sessions) >= SESSION_MAX:
		return jsonify({'message': 'Too many scan sessions - please retry in a minute'}), 500
	if 'url' not in request.json:
		return jsonify({'message': 'Invalid request'}), 400
	for suburl in request.json['url'].split('.'):
		if len(suburl) > 15:
			return jsonify({'message': 'Domain name is too long'}), 400
	try:
		session = Session(request.json.get('url'), nameserver=NAMESERVER, thread_count=THREAD_COUNT)
	except Exception as err:
		return jsonify({'message': 'Invalid domain name'}), 400
	else:
		session.scan()
		sessions.append(session)
	return jsonify(session.status()), 201


@app.route('/api/scans/<sid>')
def api_status(sid):
	for s in sessions:
		if s.id == sid:
			return jsonify(s.status())
	return jsonify({'message': 'Scan session not found'}), 404


@app.route('/api/scans/<sid>/domains')
def api_domains(sid):
	for s in sessions:
		if s.id == sid:
			return jsonify(s.domains())
	return jsonify({'message': 'Scan session not found'}), 404


@app.route('/api/scans/<sid>/stop', methods=['POST'])
def api_stop(sid):
	for s in sessions:
		if s.id == sid:
			s.stop()
			return jsonify({})
	return jsonify({'message': 'Scan session not found'}), 404


@app.route('/api/healthcheck')
def api_healthcheck():
	return jsonify({'message': 'OK'})


if __name__ == '__main__':
	app.run(host=HOST, port=PORT)