from numpy import polyfit, polyval
import requests
from bs4 import BeautifulSoup as BSoup
import pandas as pd
import csv
import requests
import os
from datetime import datetime, timedelta
from SecFiling10Q import SecFiling10Q
from SecFiling10K import SecFiling10K

class CanslimParams():
    def __init__(self, ticker, all10QsDf, all10KsDf):
        self.ticker = ticker
        ## Format the 'date' column into datetime format
        self.all10QsDf = all10QsDf
        self.all10KsDf = all10KsDf
#        self.today = datetime.now()
#        self.fiveYearsAgo = self.today - timedelta(days=5*365.25)
        self.currentQ = ""
        self.currentY = ""
        self.quartersList = []
        self.yearsList = []
        self.all10QFilings = {}
        self.all10KFilings = {}
        self.savedContextIds = {}
        self.n10Ks = 0
        self.n10Qs = 0
        self.errorLog = []

        
    def loadData(self, downloadPath = "SECDATA", oldestDate = None):
        """Loads the relevant SEC filings for analysis.
        
        Loads the last 4 10-K filings and the last 16(?) 10-Q filings. If necessary, 
        retrieves them from EDGAR and saves the raw files.
        """
        if not oldestDate:
            oldestDate = datetime.now() - timedelta(days=5*365.25)
        ## TODO: Look through the idx database and find all filings available for 'ticker'. -> in main()
        self.all10QFilings = {}
        self.all10KFilings = {}
        n10Qs = len(self.all10QsDf)
        n10Ks = len(self.all10KsDf)
        if n10Qs == 0 and n10Ks == 0:
            return False
        ## The following loops lend themselves to parallelizing, if that's possible
        ## Create a dict of all the 10Q-filings objects
        mostRecentDate = oldestDate
        for i in range(0, n10Qs):
            ## Only load/download filing if newer than the requested oldest date.
            ## Note, compares FILING date, not report date, to oldestDate.
            if (self.all10QsDf.iloc[i].date.to_pydatetime()) > oldestDate:
                filing = SecFiling10Q(self.ticker)
                ## Download file if necessary, and generate the file name
                fname = filing.download(self.all10QsDf.iloc[i].cik, \
                                        self.all10QsDf.iloc[i].conm, \
                                        self.all10QsDf.iloc[i].type, \
                                        self.all10QsDf.iloc[i].date.strftime("%Y-%m-%f"), \
                                        self.all10QsDf.iloc[i].path, \
                                        downloadPath)
                ## Load the file into the object instance
                try:
                    filing.load(fname)
                except BaseException as be:
                    self.errorLog.append("CanslimParams: Unable to open filing {:s}.".format(fname))
                    self.errorLog.append(be)
                    self.errorLog.append(filing.popErrors())
                    return False
                ## Note that the report date is not the filing due date, i.e. will calculate to be the
                ## quarter AFTER the one the report is about.
                reportDate = self.all10QsDf.iloc[i].date
                ## Use the year+quarter (for filing date) information to create a key into the dict
                quarterKey = "{:d}-Q{:d}".format(reportDate.year, int((reportDate.month - 1) / 3 + 1))
                ## TODO: verify that each filing was successfully loaded
                self.all10QFilings[quarterKey] = filing
                ## find the date of the most recent filing, to determine the "current quarter"
                if reportDate > mostRecentDate:
                    mostRecentDate = reportDate
                    self.currentQ = quarterKey
                    
        # Create a dict of all the 10K-filing objects:
        mostRecentDate = oldestDate
        for i in range(0, n10Ks):
            if (self.all10KsDf.iloc[i].date.to_pydatetime()) > oldestDate:
                filing = SecFiling10K(self.ticker)
                ## Download file if necessary, and generate the file name
                fname = filing.download(self.all10KsDf.iloc[i].cik, \
                                        self.all10KsDf.iloc[i].conm, \
                                        self.all10KsDf.iloc[i].type, \
                                        self.all10KsDf.iloc[i].date.strftime("%Y-%m-%f"), \
                                        self.all10KsDf.iloc[i].path, \
                                        downloadPath)
                ## Load the file into the object instance
                try:
                    filing.load(fname)
                except BaseException as be:
                    self.errorLog.append("CanslimParams: Unable to open filing {:s}.".format(fname))
                    self.errorLog.append(be)
                    self.errorLog.append(filing.popErrors())
                    return False
                reportDate = self.all10KsDf.iloc[i].date
                ## Use the year+quarter (for filing date) information to create a key into the dict
                yearKey = "Y{:d}".format(reportDate.year)
                ## TODO: verify that each filing was successfully loaded
                self.all10KFilings[yearKey] = filing
                ## find the date of the most recent filing, to determine the "current year"
                if reportDate > mostRecentDate:
                    mostRecentDate = reportDate
                    self.currentY = yearKey
        ## Update these with the actual number of filings that were loaded.
        self.n10Ks = len(self.all10KFilings)
        self.n10Qs = len(self.all10QFilings)
        self.errorLog.append("CanslimParams: Loaded {:d} 10Q's and {:d} 10K's.".format(n10Qs, n10Ks))
        self.errorLog.append(", ".join(k for k in self.all10QFilings))
        self.errorLog.append(", ".join(k for k in self.all10KFilings))
        self.errorLog.append("CanslimParams: Current year = {:s}, current quarter = {:s}.".format(self.currentY, self.currentQ))
        return True
    
                
    def __getQuarter(self, q):
        """Returns the quarter-key for the requested quarter in the past.
        
        The format of the quarter-key is 'Ynnnn-Qm' and is intended to be used to index into the all10QFilings-dict of 
        SecFiling10Q instances.
        """
        if abs(q) > 20:
            return None
        if not self.quartersList:
            currentYear = int(self.currentQ.split("-Q")[0])
            currentQuarter = int(self.currentQ.split("-Q")[1])
            self.quartersList.append(self.currentQ)
            quarter = currentQuarter
            year = currentYear
            for i in range(1, 20):
                quarter = quarter - 1
                if quarter < 1:
                    quarter = quarter + 4
                    year = year - 1
                self.quartersList.append("{:d}-Q{:d}".format(year, quarter))
        return self.quartersList[abs(q)]
    
    
    def __getYear(self, y):
        """Returns the year-key for the requested year in the past.
        
        The format of the year-key is 'Ynnnn' and is intended to be used to index into the all10KFilings-dict of 
        SecFiling10K instances.
        """
        if abs(y) > 5:
            return None
        if not self.yearsList:
            currentYear = int(self.currentY[1:])
            for i in range(0, 5):
                year = currentYear - i
                self.yearsList.append("Y{:d}".format(year))
        return self.yearsList[abs(y)]
    
    
    def __slope(self, xf, xi, yf, yi):
        """Calculates the slope as (yf-yi)/(xf-xi)."""
        if (xf - xi) == 0.0:
            return 0.0

        return float((yf - yi) / (xf - xi))
        
        
    def getEpsQuarter(self, quarter):
        """Returns the EPS for the specified quarter.
        
        The quarter is specified as an integer counting backwards, e.g. 0 (zero) is the current quarter,
        -1 (minus one) is the previous quarter, etc. For readability, the minus sign is required. Only 
        integers between -15 and 0 are allowed.
        """
        if quarter > -16:
            qKey = self.__getQuarter(quarter)
            try:
                eps = (self.all10QFilings)[qKey].getEps()
                ## This is annoying, but save the current contextId for use in getSales later
                self.savedContextIds[qKey] = self.all10QFilings[qKey].getCurrentContextId()
            except KeyError:
                ## Some/most/all? companies submit the 10-K *instead* of the 10-Q for that quarter.
                ## So I have to calculate the values for that quarter from the 10-K and preceding 3 10-Q's.
                ## If the missing Q is Q1, then the preceding 3 10's are from the prior year.
                ## Make sure we have all the historical data we need:
                if (quarter - 3) < -19:
                    return None
                try:
                    year10KKey = "Y" + qKey[:4]
                    yearEps = self.all10KFilings[year10KKey].getEps()
                    self.savedContextIds[qKey] = self.all10KFilings[year10KKey].getCurrentContextId()
                    
                    last1QKey = self.__getQuarter(quarter - 1)
                    last1Eps = self.all10QFilings[last1QKey].getEps()
                    self.savedContextIds[last1QKey] = self.all10QFilings[last1QKey].getCurrentContextId()
                    
                    last2QKey = self.__getQuarter(quarter - 2)
                    last2Eps = self.all10QFilings[last2QKey].getEps()
                    self.savedContextIds[last2QKey] = self.all10QFilings[last2QKey].getCurrentContextId()
                    
                    last3QKey = self.__getQuarter(quarter - 3)
                    last3Eps = self.all10QFilings[last3QKey].getEps()
                    self.savedContextIds[last3QKey] = self.all10QFilings[last3QKey].getCurrentContextId()
                    eps = yearEps - last1Eps - last2Eps - last3Eps
                except BaseException as be:
                    self.errorLog.append("CanslimParams: Unable to infer EPS from the last few filings for quarter {:s}.".format(qKey))
                    self.errorLog.append(be)
                    self.appendAllSecFilingErrorsToLog()
                    return None
            return eps
        return None
    
    
    def getEpsAnnual(self, year):
        """Returns the EPS for the specified year.
        
        The year is specified as an integer counting backwards, e.g. 0 (zero) is the most recent reported year,
        -1 (minus one) is the previous year, etc. For readability, the minus sign is required. Only 
        integers between -3 and 0 are allowed.
        """
        if year > -5:
            yKey = self.__getYear(year)
            if yKey in self.all10KFilings:
                eps = self.all10KFilings[yKey].getEps()
                self.savedContextIds[yKey] = self.all10KFilings[yKey].getCurrentContextId()
                return eps
        return None
    
    
    def getNetIncomeQuarter(self, quarter):
        """Return the Net Income for the specified quarter.
        
        The quarter is specified as an integer counting backwards, e.g. 0 (zero) is the current quarter,
        -1 (minus one) is the previous quarter, etc. For readability, the minus sign is required. Only 
        integers between -15 and 0 are allowed.
        """
    
        if quarter > -16:
            qKey = self.__getQuarter(quarter)
            try:
                NI = (self.all10QFilings)[qKey].getNetIncome()
            except KeyError:
                ## Some/most/all? companies submit the 10-K *instead* of the 10-Q for that quarter.
                ## So I have to calculate the values for that quarter from the 10-K and preceding 3 10-Q's.
                ## If the missing Q is Q1, then the preceding 3 10's are from the prior year.
                ## Make sure we have all the historical data we need:
                if (quarter - 3) < -19:
                    return None
                try:
                    year10KKey = "Y" + qKey[:4]
                    yearNI = self.all10KFilings[year10KKey].getNetIncome()
                    
                    last1QKey = self.__getQuarter(quarter - 1)
                    last1NI = self.all10QFilings[last1QKey].getNetIncome()
                    
                    last2QKey = self.__getQuarter(quarter - 2)
                    last2NI = self.all10QFilings[last2QKey].getNetIncome()
                    
                    last3QKey = self.__getQuarter(quarter - 3)
                    last3NI = self.all10QFilings[last3QKey].getNetIncome()
                    NI = yearNI - last1NI - last2NI - last3NI
                except BaseException as be:
                    self.errorLog.append("CanslimParams: Unable to infer Net Income from the last few filings for quarter {:s}.".format(qKey))
                    self.errorLog.append(be)
                    self.appendAllSecFilingErrorsToLog()
                    return None
            return NI
        return None
        
    
    def getStockholdersEquityQuarter(self, quarter):
        """Return the Net Income for the specified quarter.
        
        The quarter is specified as an integer counting backwards, e.g. 0 (zero) is the current quarter,
        -1 (minus one) is the previous quarter, etc. For readability, the minus sign is required. Only 
        integers between -15 and 0 are allowed.
        """
    
        if quarter > -16:
            qKey = self.__getQuarter(quarter)
            try:
                SE = (self.all10QFilings)[qKey].getStockholdersEquity()
            except KeyError:
                ## Some/most/all? companies submit the 10-K *instead* of the 10-Q for that quarter.
                ## So I have to calculate the values for that quarter from the 10-K and preceding 3 10-Q's.
                ## If the missing Q is Q1, then the preceding 3 10's are from the prior year.
                ## Make sure we have all the historical data we need:
                if (quarter - 3) < -19:
                    return None
                try:
                    year10KKey = "Y" + qKey[:4]
                    yearSE = self.all10KFilings[year10KKey].getStockholdersEquity()
                    
                    # last1QKey = self.__getQuarter(quarter - 1)
                    # last1SE = self.all10QFilings[last1QKey].getStockholdersEquity()
                    
                    # last2QKey = self.__getQuarter(quarter - 2)
                    # last2SE = self.all10QFilings[last2QKey].getStockholdersEquity()
                    
                    # last3QKey = self.__getQuarter(quarter - 3)
                    # last3SE = self.all10QFilings[last3QKey].getStockholdersEquity()
                    SE = yearSE
                except BaseException as be:
                    self.errorLog.append("CanslimParams: Unable to infer Net Income from the last few filings for quarter {:s}.".format(qKey))
                    self.errorLog.append(be)
                    self.appendAllSecFilingErrorsToLog()
                    return None
            return SE
        return None
        
        
    def getRoeTTM(self):
        """Returns the Return on Equity over the last four quarters (TTM).
        
        ROE is calculated as:
        
            (Net Income) / (Stockholders' Equity).
        """
        roe = 0.0
        # Calculate the change in Net Income and Stockholders' Equity over the last twelve months,
        # and find the ratio.
        roe = 0.0
        niSum = 0.0
        ni0 = self.getNetIncomeQuarter(0)
        ni1 = self.getNetIncomeQuarter(-1)
        ni2 = self.getNetIncomeQuarter(-2)
        ni3 = self.getNetIncomeQuarter(-3)
        if ni0 and ni1 and ni2 and ni3:
            niSum = ni0 + ni1 + ni2 + ni3
        else:
            print("Unable to retrieve Net Income for quarter 0, -1, -2, -3 or all.")
        seAvg = 0.0
        se0 = self.getStockholdersEquityQuarter(0)
        se1 = self.getStockholdersEquityQuarter(-1)
        se2 = self.getStockholdersEquityQuarter(-2)
        se3 = self.getStockholdersEquityQuarter(-3)
        if se0 and se1 and se2 and se3:
            seAvg = (se0 + se1 + se2 + se3) * 0.25
        else:
            print("Unable to retrieve Stockholders' Equity for quarter 0 or -4 or both.")
        if (seAvg != 0.0):
            roe = niSum / seAvg
        # Make roe negative if both S.E. and N.I. have decreased over the last year.
        if seAvg < 0.0 and niSum < 0.0:
            roe *= -1.0
        # Multiply by 100 to make a percentage.
        return roe * 100.0
    
    
    def getSalesQuarter(self, quarter):
        """Returns the Sales for the specified quarter.
        
        The quarter is specified as an integer counting backwards, e.g. 0 (zero) is the current quarter,
        -1 (minus one) is the previous quarter, etc. For readability, the minus sign is required. Only 
        integers between -15 and 0 are allowed.
        """
        if quarter > -16:
            qKey = self.__getQuarter(quarter)
            contextIdKey = ""
            try:
                contextIdKey = self.savedContextIds[qKey]
            except BaseException as be:
                self.errorLog.append(be)
                self.errorLog.append("CanslimParams: Unable to find quarter in list of saved Ids:\n{:s}".format(qKey))
                self.errorLog.append(self.savedContextIds)
            try:
                sales = self.all10QFilings[qKey].getSales(contextIdKey)            
            except BaseException as be:
                self.errorLog.append("CanslimParams: Error getting Sales for quarter {:s}. The filing may not exist, falling on inferring sales from the last few filings.". format(qKey))
                self.errorLog.append(be)
                self.appendAllSecFilingErrorsToLog()
                ## Some/most/all? companies submit the 10-K *instead* of the 10-Q for that quarter.
                ## So I have to calculate the values for that quarter from the 10-K and preceding 3 10-Q's.
                ## If the missing Q is Q1, then the preceding 3 10's are from the prior year.
                ## Make sure we have all the historical data we need:
                if (quarter - 3) < -self.n10Qs:
                    return None
                year10KKey = "Y" + qKey[:4]
                last1QKey = self.__getQuarter(quarter - 1)
                last2QKey = self.__getQuarter(quarter - 2)
                last3QKey = self.__getQuarter(quarter - 3)
                try:
                    sales = self.all10KFilings[year10KKey].getSales(self.savedContextIds[year10KKey]) \
                        - self.all10QFilings[last1QKey].getSales(self.savedContextIds[last1QKey]) \
                        - self.all10QFilings[last2QKey].getSales(self.savedContextIds[last2QKey]) \
                        - self.all10QFilings[last3QKey].getSales(self.savedContextIds[last3QKey])
                except BaseException as be:
                    self.errorLog.append("CanslimParams: Unable to determine sales.")
                    self.errorLog.append(be)
                    self.appendAllSecFilingErrorsToLog()
                    return None
            return sales
        return None
    
    
    def getSalesAnnual(self, year):
        """Returns the Sales for the specified year.
        
        The year is specified as an integer counting backwards, e.g. 0 (zero) is the most recent reported year,
        -1 (minus one) is the previous year, etc. For readability, the minus sign is required. Only 
        integers between -3 and 0 are allowed.
        """
        if year > -5:
            yKey = self.__getYear(year)
            if yKey in self.all10KFilings:
                return self.all10KFilings[yKey].getSales()
        return None
    
        
    def getEpsGrowthQuarter(self, q1, q2):
        """Calculates the EPS growth (%) for quarter q1 compared to q2.
        
        The EPS growth is calculated as the ratio EPS(q1)/EPS(q2) * 100%.
        """
        epsQ1 = self.getEpsQuarter(q1)
        epsQ2 = self.getEpsQuarter(q2)
        try:
            growth = (epsQ1 / epsQ2) * 100.
        except:
            self.errorLog.append("CanslimParams: Unable to determine quarterly EPS growth between quarters {:d} and {:d}.".format(q1, q2))
            self.appendAllSecFilingErrorsToLog()
            growth = None
        return growth
    
    
    def getEpsGrowthAnnual(self, a1, a2):
        """Calculates the EPS growth (%) for year a1 compared to a2.
        
        The EPS growth is calculated as the ratio EPS(a1)/EPS(a2) * 100%.
        """
        epsY1 = self.getEpsAnnual(a1)
        epsY2 = self.getEpsAnnual(a2)
        try:
            growth = (epsY1 / epsY2) * 100.
        except:
            self.errorLog.append("CanslimParams: Unable to determine annual EPS growth between years {:d} and {:d}.".format(a1, a2))
            self.appendAllSecFilingErrorsToLog()
            growth = None
        return growth
        
        
    def getEpsGrowthRateQuarter(self, q1, q2):
        """Calculates the growth rate from q1 to q2 as the slope between two points."""
        if q1 > -16 and q2 > -16:
            date1 = None
            try:
                date1 = self.all10QFilings[self.__getQuarter(q1)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                diff = int((self.__getQuarter(q1))[:4]) - int(self.currentY[1:])
                yKey1 = self.__getYear(diff)
                if yKey1 in self.all10KFilings:
                    date1 = self.all10KFilings[yKey1].getReportDate()
                else:
                    self.errorLog.append("CanslimParams: Year not found in filings: {:s}.".format(yKey1))
                    self.appendAllSecFilingErrorsToLog()
            date2 = None
            try:
                date2 = self.all10QFilings[self.__getQuarter(q2)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                diff = int((self.__getQuarter(q2))[:4]) - int(self.currentY[1:])
                yKey2 = self.__getYear(diff)
                if yKey2 in self.all10KFilings:
                    date2 = self.all10KFilings[yKey2].getReportDate()
                else:
                    self.errorLog.append("CanslimParams: Year not found in filings: {:s}.".format(yKey2))
                    self.appendAllSecFilingErrorsToLog()
            eps1 = self.getEpsQuarter(q1)
            eps2 = self.getEpsQuarter(q2)
            try:
                rate = self.__slope((date2 - date1).days, 0.0, eps2, eps1)
            except BaseException as be:
                self.errorLog.append("CanslimParams: Unable to determine quarterly EPS growth rate for quarters {:s} and {:s}.".format(str(q1), str(q2)))
                self.errorLog.append(str(be))
                self.appendAllSecFilingErrorsToLog()
                return None
            return rate
        return None
    
    
    def getStabilityOfEpsGrowth(self, numQuarters):
        """Calculates the stability of the quarterly EPS growth over the last numQuarters (<20).
        
        The stability is calculated as the amount of deviation from the best-fit-line growth. 
        In other words, a line is fitted through the data, and the goodness-of-fit is determined.
        """
        if numQuarters < 16:
            x = []
            y = []
            firstDate = None
            try:
                firstDate = self.all10QFilings[self.__getQuarter(0)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                firstDate = self.all10KFilings[self.__getYear(0)].getReportDate()
            ## create the arrays of EPS vs nDays (from most recent filing) values
            for i in range(0, -numQuarters, -1):
                qKey = self.__getQuarter(i)
                eps = self.getEpsQuarter(i)
                if eps:
                    y.append(eps)
                    try:
                        x.append((self.all10QFilings[qKey].getReportDate() - firstDate).days)
                    except:
                        ## Locate the 10-K submitted instead of the 10-Q
                        diff = int(qKey[:4]) - int(self.currentY[1:])
                        yKey = self.__getYear(diff)
                        if yKey in self.all10KFilings:
                            x.append((self.all10KFilings[yKey].getReportDate() - firstDate).days)
                        else:
                            self.errorLog.append("CanslimParams: Year not found: {:s}".format(yKey))
            ## Fit a polynomial of degree 2 through the data: ax**2 + bx + c. 'a' should be the acceleration
            try:
                p = polyfit(x, y, 2)
            except BaseException as be:
                self.errorLog.append("CanslimParams: Unable to determine Stability of EPS Growth.")
                self.errorLog.append("CanslimParams: x= {:s}, y= {:s}".format((",".join(str(i) for i in x)), (",".join(str(j) for j in y))))
                self.errorLog.append(str(be))
                self.appendAllSecFilingErrorsToLog()
                return None
            yfit = polyval(p, x)
            sigma = (y - yfit) / y
            error = sigma * sigma
            res = 1.0 / error.sum()
            return res
        return None
    
    
    def getEpsGrowthAcceleration(self, numQuarters):
        """Returns the (mean) acceleration of EPS growth over the specified number of quarters.
        
        The acceleration is calculated as the second derivative of the data. numQuarters is required to 
        be between 2 and 15. At least three quarters are necessary to calculate acceleration.
        """
        if numQuarters < 16:
            x = []
            y = []
            firstDate = None
            try:
                firstDate = self.all10QFilings[self.__getQuarter(0)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                firstDate = self.all10KFilings[self.__getYear(0)].getReportDate()
            ## create the arrays of EPS vs nDays (from most recent filing) values
            for i in range(0, -numQuarters, -1):
                qKey = self.__getQuarter(i)
                eps = self.getEpsQuarter(i)
                if eps:
                    y.append(eps)
                    try:
                        x.append((self.all10QFilings[qKey].getReportDate() - firstDate).days)
                    except:
                        ## Locate the 10-K submitted instead of the 10-Q
                        diff = int(qKey[:4]) - int(self.currentY[1:])
                        yKey = self.__getYear(diff)
                        if yKey in self.all10KFilings:
                            x.append((self.all10KFilings[yKey].getReportDate() - firstDate).days)
                        else:
                            self.errorLog.append("CanslimParams: Year not found: {:s}".format(yKey))
            ## Fit a polynomial of degree 2 through the data: ax**2 + bx + c. 'a' should be the acceleration
            try:
                p = polyfit(x, y, 2)
            except BaseException as be:
                self.errorLog.append("CanslimParams: Unable to determine EPS Growth Acceleration.")
                self.errorLog.append("CanslimParams: x= {:s}, y= {:s}".format((",".join(str(i) for i in x)), (",".join(str(j) for j in y))))
                self.errorLog.append(str(be))
                self.appendAllSecFilingErrorsToLog()
                return None
            return p
        return None
    
    
    def getSalesGrowthQuarter(self, q1, q2):
        """Calculates the Sales growth (%) for quarter q1 compared to q2.
        
        The Sales growth is calculated as the ratio Sales(q1)/Sales(q2) * 100%.
        """
        salesQ1 = self.getSalesQuarter(q1)
        salesQ2 = self.getSalesQuarter(q2)
        try:
            growth = (salesQ1 / salesQ2) * 100.
        except:
            self.errorLog.append("CanslimParams: Unable to determine quarterly Sales growth between quarters {:d} and {:d}.".format(q1, q2))
            self.appendAllSecFilingErrorsToLog()
            growth = None
        return growth
     
     
    def getSalesGrowthRateQuarter(self, q1, q2):
        """Calculates the growth rate from q1 to q2 as the slope between two points."""
        if q1 > -16 and q2 > -16:
            date1 = None
            try:
                date1 = self.all10QFilings[self.__getQuarter(q1)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                diff = int((self.__getQuarter(q1))[:4]) - int(self.currentY[1:])
                yKey1 = self.__getYear(diff)
                if yKey1 in self.all10KFilings:
                    date1 = self.all10KFilings[yKey1].getReportDate()
                else:
                    self.errorLog.append("CanslimParams: Year not found in filings: {:s}.".format(yKey1))
            date2 = None
            try:
                date2 = self.all10QFilings[self.__getQuarter(q2)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                diff = int((self.__getQuarter(q2))[:4]) - int(self.currentY[1:])
                yKey2 = self.__getYear(diff)
                if yKey2 in self.all10KFilings:
                    date2 = self.all10KFilings[yKey2].getReportDate()
                else:
                    self.errorLog.append("CanslimParams: Year not found in filings: {:s}.".format(yKey2))
            sales1 = self.getSalesQuarter(q1)
            sales2 = self.getSalesQuarter(q2)
            try:
                rate = self.__slope((date2 - date1).days, 0.0, sales2, sales1)
            except BaseException as be:
                self.errorLog.append("CanslimParams: Unable to determine sales growth rate between quarters {:d} and {:d}.".format(q1, q2))
                self.errorLog.append(be)
                self.appendAllSecFilingErrorsToLog()
                return None
            return rate
        return None
    
    
    def getSalesGrowthAcceleration(self, numQuarters):
        """Returns the (mean) acceleration of Sales growth over the specified number of quarters.
        
        The acceleration is calculated as the second derivative of the data. numQuarters is required to 
        be between 2 and 15. At least three quarters are necessary to calculate acceleration.
        """
        if numQuarters < 16:
            x = []
            y = []
            firstDate = None
            try:
                firstDate = self.all10QFilings[self.__getQuarter(0)].getReportDate()
            except:
                ## If the 10-Q for the current quarter is missing, there should be a 10-K instead
                firstDate = self.all10KFilings[self.__getYear(0)].getReportDate()
            ## create the arrays of EPS vs nDays (from most recent filing) values
            for i in range(0, -numQuarters, -1):
                qKey = self.__getQuarter(i)
                sales = self.getSalesQuarter(i)
                if sales:
                    y.append(sales)
                    try:
                        x.append((self.all10QFilings[qKey].getReportDate() - firstDate).days)
                    except:
                        ## Locate the 10-K submitted instead of the 10-Q
                        diff = int(qKey[:4]) - int(self.currentY[1:])
                        yKey = self.__getYear(diff)
                        if yKey in self.all10KFilings:
                            x.append((self.all10KFilings[yKey].getReportDate() - firstDate).days)
                        else:
                            self.errorLog.append("CanslimParams: Year not found: {:s}".format(yKey))
                else:
                    self.errorLog.append("Unable to get the sales data for this quarter: {:d}".format(i))
            ## Fit a polynomial of degree 2 through the data: ax**2 + bx + c. 'a' should be the acceleration
            try:
                p = polyfit(x, y, 2)
            except BaseException as be:
                self.errorLog.append("CanslimParams: Unable to determine Sales Growth Acceleration.")
                self.errorLog.append("CanslimParams: x= {:s}, y= {:s}".format((",".join(str(i) for i in x)), (",".join(str(j) for j in y))))
                self.errorLog.append(str(be))
                self.appendAllSecFilingErrorsToLog()
                return None
            return p
        return None
    
    
    def logErrors(self):
        from os.path import join
        with open(join("Logs", "{:s}_log.txt".format(self.ticker)), "w+") as f:
            for item in self.errorLog:
                f.write("{:s}\n".format(str(item)))
    

    def appendAllSecFilingErrorsToLog(self):
        """Iterates over all SecFiling objects, retrieves their errors, and appends them to self.errorLog."""
        ## Go through all the SecFilings and retrieve error messages, if any.
        for k in self.all10QFilings:
            errString = ""
            errString = self.all10QFilings[k].popErrors()
            if errString:
                self.errorLog.append("{:s} : {:s}".format(k, errString))
        for k in self.all10KFilings:
            errString = ""
            errString = self.all10KFilings[k].popErrors()
            if errString:
                self.errorLog.append("{:s} : {:s}".format(k, errString))
            
            
    def plotEpsQuarter(self):
        """Generates a log-plot of quarterly EPS data."""
        pass
    
    def plotStockData(self):
        """Generates a plot of the weekly stock data for the last three years."""
        pass
    
    def getStockData(self):
        """Download the weekly stock data for the last three years from somehwere."""
        pass
    
    def getStockGrowth(self):
        """Returns the stock growth as the slope of the best-fit line through the stock data."""
        pass
    
    def getStockAcceleration(self):
        """Fits the equation a*x^2+b*x+c through the data and returns the 'a' coefficient."""
        pass
    
    ## Lofty future goal: write algorithm(s) that identifies Canslim patterns in the stock data
        