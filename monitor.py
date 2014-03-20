#-------------------------------------------------------------------------------
# Name:        monitor.py
# Purpose:     1. check availbility http://fawn.ifas.ufl.edu/controller.php/latestmapjson/
#              2. check data timeliness for 42 fawn stations fawn-monitor.appspot.com
#              3. check availbility  http://fdacswx.fawn.ifas.ufl.edu/index.php/read/latestobz/format/json
# Author:      Dawei Jia
#
# Created:     12/09/2013
# Copyright:   (c) DaweiJia 2013
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import logging
import json
import datetime
import database

from monitor_helper import MonitorHelper
from google.appengine.api import users
#from google.appengine.ext import webapp
from google.appengine.api import urlfetch
from google.appengine.api import mail
from google.appengine.ext import db
import webapp2

class FawnMonitor(webapp2.RequestHandler):
    '''monitor data availability and timeliness '''
    url = "http://fawn.ifas.ufl.edu/controller.php/latestmapjson/"
    stnIDList = ['260','240','241','110','280','330','450','380','311','360',
               '435','170','150','455','480','410','130','250','390','302',
               '121','304','303','230','371','270','290','320','350','460',
               '275','180','405','440','470','340','160','490','120','420',
               '140','425']
    emailList = ["jiadw007@gmail.com","lstaudt@ufl.edu","rlusher@ufl.edu","gbraun@ufl.edu","tiejiazhao@gmail.com","ohyeahfanfan@gmail.com"]
    record_time_delta = datetime.timedelta(hours = 4)
    fawnStn_time_delta = datetime.timedelta(hours = 1)
    no_update_time_delta = datetime.timedelta(hours = 2)
    def get(self,retries = 3):

        '''response request method = get'''
        MonitorHelper.checkStatusCode(self)

    def getInfo(self,result):
        '''get fawn station information'''
        decoded = MonitorHelper.parseJson(self,result)
        logging.info("Getting fawn time...")
        self.response.out.write("Getting fawn time...<br />")
        #fawn time
        alert_time = datetime.datetime.strptime(decoded['fawnTime'][:-4],'%A %B %d, %Y %I:%M %p')
        season = str(decoded['fawnTime'][-3:])
        fawnData=[]
        self.response.out.write("fawnTime: " + str(alert_time) + "  " + season)
        #build fawn station time list
        for data in decoded['stnsWxData']:
            self.response.out.write("<br />")
            fawnStn_time = datetime.datetime.strptime(data['dateTimes'][:-4],'%m/%d/%Y %I:%M %p')
            data_list = []
            data_list.append(data['stnID'])
            if data['dateTimes'][-3:] =='CST' or data['dateTimes'][-3:] =='CDT':
                data_list.append(fawnStn_time + self.__class__.fawnStn_time_delta)
                self.response.out.write(str(data['stnID']) +": "+ \
                str(fawnStn_time + self.__class__.fawnStn_time_delta) + "  " + season)
            else:
                data_list.append(fawnStn_time)
                self.response.out.write(str(data['stnID']) +": "+str(fawnStn_time) + "  " + season)
            fawnData.append(data_list)
        logging.info("Getting stnID...")
        self.response.out.write("<br />Getting fawn stnID...<br />")
        #build no update list
        no_update_list = [data for data in fawnData if alert_time - data[1] > self.__class__.no_update_time_delta]
        logging.info("Getting no update stnID...")
        self.response.out.write(len(no_update_list))
        self.response.out.write("<br />Getting no update stnID...<br />")
        #report no update stations
        if len(no_update_list) != 0:

            logging.info("number of no update stn ID is: %d", len(no_update_list))
            missingInformation ="""
            number of no update stn ID is %d<br />
            """ % len(no_update_list)
            self.response.out.write(missingInformation)
            subject = "FAWN ALERT NO UPDATE @ " + str(alert_time)
            #build email content
            html = MonitorHelper.buildEmailContent(self,no_update_list,season)
            self.response.out.write(html)
            #query last record in the database
            q = db.GqlQuery("SELECT * FROM Record \
                             WHERE error_code = '200'\
                             ORDER BY record_time DESC")
            queryResult = q.get()
            message = ",".join([data[0] for data in no_update_list])
            message_time = ",".join([str(data[1]) for data in no_update_list])
            self.response.out.write("Check last record in the database<br/>")
            if queryResult is None or message_time not in queryResult.error_time or message not in queryResult.error_details :

                record = database.Record(error_code = str(result.status_code),error_details = message)
                MonitorHelper.updateRecord(self, record, alert_time,message_time)
                MonitorHelper.emailErrorInfo(self.__class__.emailList,self,subject,html)
        else:
            MonitorHelper.allGoodInfo(self)


class FdacsMonitor(webapp2.RequestHandler):
    '''Fdacs Monitor'''
    default_emailList =["uffawn@gmail.com"]
    url = "http://fdacswx.fawn.ifas.ufl.edu/index.php/read/latestobz/format/json"
    vendor_url = "http://fdacswx.fawn.ifas.ufl.edu/index.php/read/station/format/json"
    record_time_delta = datetime.timedelta(hours = 4)
    emailList=[]
    def get(self,retries = 3):

        '''response request method = get'''
        MonitorHelper.checkStatusCode(self)

    def getInfo(self,result):

        '''get Fdacs station infomation'''
        #parse json
        decoded = MonitorHelper.parseJson(self,result)
        logging.info("Getting fresh status")
        self.response.out.write("Getting fresh status...<br />")
        total_stns_num = len(decoded)
        self.response.out.write("There are total %d stations.<br />" % total_stns_num)
        #fresh status
        fresh_false_list = [data for data in decoded if data['fresh'] == False]
        false_stns_num = len(fresh_false_list)
        self.response.out.write("There are %d false fresh status stations.<br />" % false_stns_num)
        #report no update stations
        if false_stns_num != 0:
            alert_time = datetime.datetime.now() - self.__class__.record_time_delta
            subject = "FDACS %d ALERT NO UPDATE @ %s" %(false_stns_num, str(alert_time)[:-7])
            self.response.out.write(subject + "<br />")
            #set email list
            if false_stns_num >= total_stns_num / 2:
                self.__class__.emailList = self.__class__.default_emailList[:]
                self.__class__.emailList.append("tiejiazhao@gmail.com")
            else:
                self.__class__.emailList = self.__class__.default_emailList[:]

            vendor_lists= json.loads(urlfetch.fetch(self.__class__.vendor_url).content)
            vendor_dict = {}
            for vendor in vendor_lists:
                vendor_dict[vendor['id']] = vendor
                ##resp.response.out.write(vendor_dict[vendor['id']])
            #build no update list
            no_update_list = []
            for data in fresh_false_list:
                data_list = []
                data_list.append(data["station_id"])
                ##resp.response.out.write(vendor_dict[data["station_id"]]['vendor_name'])
                data_list.append(data["standard_date_time"])
                data_list.append(vendor_dict[data["station_id"]]['vendor_station_id'])
                data_list.append(vendor_dict[data["station_id"]]['vendor_name'])
                logging.info(data_list)
                ##resp.response.out.write(str(data_list) + "<br />")
                no_update_list.append(data_list)

            #build email content
            html = MonitorHelper.buildEmailContent(self,no_update_list)
            self.response.out.write(html)
            #query last record in the database
            q = db.GqlQuery("SELECT * FROM FdacsRecord \
                             WHERE error_code = '200'\
                             ORDER BY record_time DESC")
            queryResult = q.get()
            message = ",".join([data[0] for data in no_update_list])
            message_time = ",".join([data[1] for data in no_update_list])
            self.response.out.write("Check last record in the database<br/>")
            if queryResult is None or message_time not in queryResult.error_time or message not in queryResult.error_details :

                record = database.FdacsRecord(error_code = str(result.status_code),error_details = message)
                MonitorHelper.updateRecord(self, record, alert_time,message_time)
                MonitorHelper.emailErrorInfo(self.__class__.emailList,self,subject,html)

        else:
            #all stations are good
            MonitorHelper.allGoodInfo(self)

application = webapp2.WSGIApplication(
                                    [('/fawn/monitor',FawnMonitor),
                                     ('/fdacs/monitor',FdacsMonitor)],
                                    debug = True)
