import requests
from bs4 import BeautifulSoup as BSoup
import pandas as pd
import csv
import requests
import os
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import traceback

class SecFiling(ABC):
    """Holds the data of a generic SEC filing.
    
    Expected to be subclassed by 'SecFiling10K' and 'SecFiling10Q'. Also expected to be a utility to CanslimParams, i.e.
    driven by it.
    
    Before running this, make sure my edgar_idx.db is up-to-date. analyze_stockdata.get_list_sec_filings() will 
    update the 'idx' table (i.e. the database with the relevant urls), and analyze_stockdata.get_cik_ticker_lookup_db()
    will update the lookup table for CIK number - ticker symbol correlation.
    """
    def __init__(self, ticker):
        self.ticker = ticker
        self.xbrlInstance = None
        self.contextIds = {}
        self.currentContextId = ""
        self.errorLog = []
        self.currentSE = None
        self.currentNI = None
        self.reportDate = None
        
        
    def __del__(self):
        self.contextIds.clear()
        del self.errorLog[:]
        
    
    def getReportDate(self):
        return self.reportDate
        
        
    def download(self, cik, co_name, filing_type, filing_date, filing_link, downloadPath = "SECDATA"):
        """Retrieves a SEC filing from EDGAR. Follow by a call to 'load()'.
        
        Also a roundabout way of getting the filename for this data file.
        """
        # inspired by http://kaikaichen.com/?p=681
        saveas = '_'.join([cik, co_name, filing_type, str(filing_date)])
        saveDir = os.path.join(downloadPath, co_name)
        self.fname = os.path.join (saveDir, saveas)
        ## Only download if the file doesn't exist yet (at the expected path)
        if not os.path.exists(self.fname):
            url = 'https://www.sec.gov/Archives/' + filing_link.strip()
            if not os.path.exists(saveDir):
                os.makedirs(saveDir)
            with open("logfile.txt", "a+") as logfile:
                with open(self.fname, 'wb') as f:
                    try:
                        f.write(requests.get('%s' % url).content)
                        logfile.write('{:s} - downloaded and saved as {:s}\n'.format(url, self.fname))
                    except BaseException as be:
                        self.errorLog.append("SecFiling: Unable to download from url: {:s}".format(url))
                        self.errorLog.append(str(be))
        return (self.fname)
    
    
    def load(self, fname):
        """Loads the data of SEC filing."""
        f = open (fname, "r")
        ## TODO: Do I need to have the whole file in memory?
        wholeFile = f.read ()
        f.close ()
        soup = BSoup (wholeFile, "lxml")
        ## Extract some basic info from the SEC-header section
        sec_header = soup.find("sec-header")
        try:
            for l in sec_header.text.split("\n"):
                if 'conformed period of report' in l.lower():
                    self.reportDate = datetime.strptime((l.split(":")[1]).strip(), "%Y%m%d")
                if 'standard industrial classification' in l.lower():
                    self.stdIndustrialClass = l.split(":")[1].strip()
            self.errorLog.append("SecFiling: Report date: {:s}, industrial class: {:s}". format(str(self.reportDate), self.stdIndustrialClass))
        except:
            self.errorLog.append("SecFiling: Unable to find SEC-header in file.")
            return False
        
        ## Find the XBRL Instance document. It has the description-tag "XBRL INSTANCE DOCUMENT" within its document-tag.
        doc_tag = soup.find_all("document")
        try:
            for tag in doc_tag:
                desc_tag = tag.find("description")
                if desc_tag:
                    description = desc_tag.get_text().lower()
                    if (description.startswith("xbrl instance document")):
                        self.xbrlInstance = tag
                        break

            ## Try again, in case the first attempt didn't find an XBRL Document
            if not self.xbrlInstance:
                for tag in doc_tag:        
                    ## Sometimes the description seems to be (mis-)named by the default instance document file named.
                    ## Don't 'break', to give the first if statement priority.
                    ## The "ex-..." seems to more reliably be in the TYPE-tag than the Description-tag
                    desc_tag = tag.find("type")
                    if desc_tag:
                        description = desc_tag.get_text().lower()
                        if description.startswith("EX-101.INS".lower()):
                            self.xbrlInstance = tag
                            break
                    desc_tag = tag.find("description")
                    if desc_tag:
                        description = desc_tag.get_text().lower()
                        if description.startswith("EX-101.INS".lower()):
                            self.xbrlInstance = tag
                            break
                    
            ## Try yet again, in case the second attempt didn't find an XBRL Document either
            if not self.xbrlInstance:    
                for tag in doc_tag:
                    ## In the case of inline XBRL tags, there is no Instance document, but the SEC extracts one.
                    ## Try and find that instead, by finding an XML-tag within a description tag of "IDEA: XBRL DOCUMENT".
                    if (description.startswith("idea: xbrl document")):
                        self.errorLog.append("SecFiling: Trying to fall back on extracted instance document.\n")
                        ## I think I just want the first occurrence of this. It seems that that is the XBRL Doc.
                        if not self.xbrlInstance:
                            xml_tags = tag.find("xml")
                            #self.errorLog.append(xml_tags)
                            if xml_tags:
                                self.xbrlInstance = tag
                                break
        except:
            self.errorLog.append("SecFiling: Unable to find document-tags in file.")
            return False
        
        if not self.xbrlInstance:
            self.errorLog.append("SecFiling: ERROR: unable to find Instance document for {:s}.\n".format(self.fname))
            return False
        
        ## 'findAll('us-gaap:earningspersharebasic')' doesn't seem to work... so find them manually
        self.all_tags = self.xbrlInstance.findAll()
        if not self.all_tags:
            self.errorLog.append("SecFiling: No tags found!")
            return False
        return True
    
    
    def save(self):
        """Saves the data to file."""
        pass
     
        
    def getEps(self):
        """Retrieve the current EPS from the filing."""
        possible_tags = [\
            ## The standard tag, used by most (MMM uses all lower-case)
            'us-gaap:EarningsPerShareBasic'.lower()\
            ## NRP uses this tag (wtf?!?)
            ,'us-gaap:IncomeLossFromContinuingOperationsPerOutstandingLimitedPartnershipUnitBasicNetOfTax'.lower()\
            ## Used by OSK
            ,'us-gaap:IncomeLossFromContinuingOperationsPerBasicShare'.lower()\
            ## WK uses this tag:
            ,'us-gaap:EarningsPerShareBasicAndDiluted'.lower()\
            ]
        all_eps_tags = []
        try:
            for tag in self.all_tags:
                if tag.name.strip().lower() in possible_tags:
                    all_eps_tags.append(tag)
            self.currentEps = self.getCurrentValue(all_eps_tags)
        except:
            self.errorLog.append("SecFiling: Unable to find the EPS information in the filing.\n")
            return None
        return self.currentEps
            
        
    def getSales(self, contextId = ""):
        """Retrieves the current Sales data from the filing.
        
        WARNING! The 'currentContextRef' member must have been set first (e.g. by calling getEps or getRoe 
        before calling this function) for this function to work properly. It seems to be very tricky to 
        figure out the currentContextRef by itself."""
        if not contextId:
            if not self.currentContextId:
                self.errorLog.append("SecFiling: ERROR! current contextId is not set!\n")
                return -99.0
            else:
                contextId = self.currentContextId
        ## Collect a list of possible tags to check for to get sales. There are a lot, but so far
        ## there are no collisions within a statement for these.
        possible_tags = [\
            ## The filings seem to use either 'Revenues' or 'SalesRevenuesNet' to indicate the net sales amount
            'us-gaap:Revenues'.lower()\
            ,'us-gaap:SalesRevenuesNet'.lower()\
            ## Some of AAPL's statements use this tag:
            ,'us-gaap:salesrevenuenet'.lower()\
            ## Some of AMG's (and JNJ, OSK) statements use this tags:
            ,'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'.lower()\
            ## Some of AMG's statements also sometimes use this tag:
            ,'us-gaap:AssetManagementFees1'.lower()\
            ## The 10-Q of CRVL for 2018-Q1 (filing date 2017/12/31) uses this tag:
            ,'us-gaap:SalesRevenueServicesNet'.lower()\
            ## NRP uses this tag (hopefully it's the right one for sales)
            ,'us-gaap:IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest'.lower()\
            ## INS uses this tag:
            ,'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax'.lower()\
            ## JNJ's 10-Q for 2018Q2 uses this tag?!?:
            ,'us-gaap:NewAccountingPronouncementsAndChangesInAccountingPrinciplesTextBlock'.lower()\
            ]
        all_sales_tags = []
        try:
            for tag in self.all_tags:
                ## The filings seem to use either 'Revenues' or 'SalesRevenuesNet' to indicate the net sales amount
                ## But the 'Revenues' tag also contains other stuff, need to filter it by its contextref attribute
                if tag.name.strip().lower() in possible_tags:
                    if (tag.attrs)['contextref'] == contextId:
                        all_sales_tags.append(tag)
                # if 'us-gaap:Revenues'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # elif 'us-gaap:SalesRevenuesNet'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # Some of AAPL's statements use this tag:
                # elif 'us-gaap:salesrevenuenet'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # Some of AMG's (and JNJ, OSK) statements use one of these two tags:
                # elif 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # elif 'us-gaap:AssetManagementFees1'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # The 10-Q of CRVL for 2018-Q1 (filing date 2017/12/31) uses this tag:
                # elif 'us-gaap:SalesRevenueServicesNet'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # elif 'us-gaap:IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest'.lower() == tag.name.strip().lower():
                    # NRP uses this tag (hopefully it's the right one for sales)
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # INS uses this tag:
                # elif 'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
                # JNJ's 10-Q for 2018Q2 uses this tag?!?:
                # elif 'us-gaap:NewAccountingPronouncementsAndChangesInAccountingPrinciplesTextBlock'.lower() == tag.name.strip().lower():
                    # if (tag.attrs)['contextref'] == contextId:
                        # all_sales_tags.append(tag)
        except BaseException as be:
            self.errorLog.append("SecFiling: Unable to find Sales data in filing.")
            self.errorLog.append(be)
            return None
        if not all_sales_tags:
            self.errorLog.append("SecFiling: Sales/Revenue information not found.")
        self.currentSales = self.getCurrentValue(all_sales_tags) 
        return self.currentSales
        
        
    def getRoe(self):
        """Retrieves the current Return on Equity from the filing."""
        ## First find the stockholders' equity
        currentSE = self.getStockholdersEquity()
        ## Then find the net income
        currentNI = self.getNetIncome()
        ## Return on equity = net income / stockholders' equity
        self.currentRoe = 0.0
        if self.currentSE and self.currentNI and self.currentSE > 0.0:
            self.currentRoe = self.currentNI / self.currentSE
        # Multiply by 100 to turn it into a percentage.
        return self.currentRoe * 100.0
        
        
    def getCurrentValue(self, tagList, duration, eps):
        """Finds the tag for the current date from a list of tags, and returns its value."""
        prevDiff = timedelta(9999, 0, 0) ## days, seconds, microseconds (!)
        prevContextRefLen = 100000
        current = None
        try:
            for tag in tagList:
                ## Find the quarter that ended closest to the reportDate, make sure it's a quarter
                ## TODO: figure out how to do this for the 10-K's
                contextRef = str((tag.attrs)['contextref'])
                ## The various 'us-gaap:<quantity-of-interest>' tags can occur multiple times for the same time frame,
                ## but usually distinguish between contextRef names (i.e. the contextref attributes are different, but 
                ## denote the same time frame). It seems that I generally want the contextRef with the shortest name
                ## (i.e. least special one)?
                contextRefLen = len(contextRef)
                if contextRef in self.contextIds:
                    tag_dates = self.contextIds[contextRef]
                else:
                    tag_dates = self.getStartEndDateForContext(contextRef)
                    self.contextIds[contextRef] = tag_dates
                try:
                    diff = self.reportDate - tag_dates[1]
                    ## Find the closest enddate to the ReportDate, i.e. the 'current' date
                    if abs(diff.days) < abs(prevDiff.days): ## found a date closer to the reportDate
                        prevDiff = diff
                        ## Reset the length of the contextref string
                        prevContextRefLen = 100000
                    ## found another candidate, do all the checks
                    if abs(diff.days) <= abs(prevDiff.days): ## found a date closer to the reportDate 
                        ## If the date is an instantaneous date, only look at the 'diff'
                        if tag_dates[1] == tag_dates[0]:
                            if contextRefLen < prevContextRefLen:
                                prevContextRefLen = contextRefLen
                                current = tag
                                prevDiff = diff
                        ## If a date range is given, make sure it's about a year long
                        elif abs(abs(tag_dates[1] - tag_dates[0]).days - duration) < eps:
                            if contextRefLen < prevContextRefLen:
                                prevContextRefLen = contextRefLen
                                current = tag
                                prevDiff = diff
                except BaseException as be:
                    self.errorLog.append(str(be))
                    return None
            if current:
                self.currentContextId = (current.attrs)['contextref']
            else:
                self.errorLog.append("SecFiling: Failed to determine the value for current contextId")
                self.errorLog.append("SecFiling: Received tagList: \n" + str(tagList))
                self.errorLog.append("SecFiling: Stored contextIds: \n" + str(self.contextIds))
                return None
        except Exception as ex:
            self.errorLog.append("SecFiling: Unable to determine the current value:")
            self.errorLog.append(type(ex).__name__)
            self.errorLog.append(ex)
            self.errorLog.append(traceback.print_exc())
            return None
        return float(current.text)  
    
        
    def getStockholdersEquity(self):
        """Returns the value saved in self.currentSE.
        
        This attribute is populated by getRoe(). It is 'None' until that function is called. 
        Useful for debugging purposes. 
        """## First find the stockholders' equity
        all_se_tags = []
        self.currentSE = None
        try:
            for tag in self.all_tags:
                ## Check for all possible Stockholders' Equity- indicating tags
                if 'us-gaap:StockholdersEquity'.lower() == tag.name.strip():
                    all_se_tags.append(tag)
                elif 'us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'.lower() \
                        == tag.name.strip():
                    all_se_tags.append(tag)
            if not all_se_tags:
                self.errorLog.append("SecFiling: Stockholders' equity information not found.")
            self.currentSE = self.getCurrentValue(all_se_tags)
        except:
            if not self.currentSE:
                self.errorLog.append("SecFiling: Unable to find Stockholders' Equity in filing.")
            return None
        return self.currentSE
    
    
    def getNetIncome(self):
        """Returns the value saved in self.currentNI.
        
        This attribute is populated by getRoe(). It is 'None' until that function is called. 
        Useful for debugging purposes. 
        """
        ## Then find the net income
        all_ni_tags = []
        self.currentNI = None
        try:
            for tag in self.all_tags:
                ## Check for all possible Net Income- indicating tags
                if 'us-gaap:NetIncomeLoss'.lower() == tag.name.strip():
                    all_ni_tags.append(tag)
                elif 'us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic'.lower() == tag.name.strip():
                    all_ni_tags.append(tag)
                elif 'us-gaap:ProfitLoss'.lower() == tag.name.strip():
                    all_ni_tags.append(tag)
            if not all_ni_tags:
                self.errorLog.append("SecFiling: Net income information not found.")
            self.currentNI = self.getCurrentValue(all_ni_tags)
        except:
            if not self.currentNI:
                self.errorLog.append("SecFiling: Unable to find Net Income in filing.")
            return None
        return self.currentNI
            
            
    def getStartEndDateForContext(self, contextRef):
        """Looks up the date for the given contextref/id.

        This used to be a method under the SecFiling class. For some reason (me, Jupyter notebooks, other), 
        I would get an AttributeError that SecFiling10Q did not have this attribute when calling, e.g. 'getEps()
        on a SecFiling10Q object. So I nested it here under 'getCurrentValue'. """
        ## Some filings use 'xbrli:context' as the tag
        periodXml = self.xbrlInstance.find("xbrli:context", {"id" : contextRef})
        ## Some filings just use 'context' as the tag
        if not periodXml:
            periodXml = self.xbrlInstance.find("context", {"id" : contextRef})
        if periodXml:
            ## We found a context-tag, try to determine the dates. Again, some use 'xbrli:<tag>', some just
            ## use '<tag>'. Also, some contexts are instantaneous ('instant'), and some indicate a date range
            ## Search for each case, and search for all known variants of the tag names, just in case some
            ## filings mix between them.
            startdate = periodXml.find("xbrli:startdate") ## or just 'startdate'
            if not startdate:
                startdate = periodXml.find("startdate")
            enddate = periodXml.find("xbrli:enddate") ## or just 'enddate'
            if not enddate:
                enddate = periodXml.find("enddate")
            instant = periodXml.find("xbrli:instant") ## instantaneous date, not a date range
            if not instant:
                instant = periodXml.find("instant") ## instantaneous date, not a date range
            ## Presumably, there is either an 'instant' or a 'startdate' + 'enddate'
            if instant:
                startdate = instant
                enddate = startdate
        else:
            self.errorLog.append("SecFiling: ERROR: Unable to find dates for contextref '{:s}'".format(contextRef))
            return None
        try:
            sd = datetime.strptime(startdate.text, "%Y-%m-%d")
        except:
            sd = None
        try:
            ed = datetime.strptime(enddate.text, "%Y-%m-%d")
        except:
            ed = None
        return [sd, ed]
        
        
    def getCurrentContextId(self):
        return self.currentContextId
        
        
    def printErrors(self):
        return ", ".join(str(e) for e in self.errorLog)
            
    def popErrors(self):
        """Returns a string of all the errors, separated by '\n', and clears the error log."""
        errString = "\n".join(str(e) for e in self.errorLog)
        self.errorLog = []
        return errString
        