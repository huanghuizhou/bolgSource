---
title: 基于selenium实现自动删除qq空间留言板
date: 2019-06-29 16:09
tags: [python,脚本,爬虫]
categories:
---

py大法好，解放双手。

## 脚本环境
    python环境，selenium库，Chrome   webdriver驱动。
<!--more-->

## 源码
```python   
	# coding=utf-8
	import datetime
	import logging
	import os
	import time
	import traceback
	
	from selenium import webdriver
	from selenium.webdriver import ActionChains
	from selenium.webdriver.chrome.options import Options
	
	
	
	# 日志
	def get_logger(name):
	    log = logging.getLogger(name)
	    log.setLevel(logging.DEBUG)
	    # Standard output handler
	    sh = logging.StreamHandler()
	    sh.setLevel(logging.DEBUG)
	    sh.setFormatter(logging.Formatter('%(levelname)s - %(name)s:%(lineno)s: %(message)s'))
	    log.addHandler(sh)
	    return log
	logger = get_logger(__file__)
	
	
	def work(browser):
	    qq=1017981449
	
	    browser.get('https://user.qzone.qq.com/{}/main'.format(qq))
	    browser.switch_to.frame('login_frame')
	    time.sleep(2)
	    try:
	        browser.find_element_by_id('switcher_plogin').click()
	        browser.find_element_by_id('u').clear()
	        #你的qq账号
	        browser.find_element_by_id('u').send_keys('1017981449')
	        browser.find_element_by_id('p').clear()
	        #你的qq密码
	        browser.find_element_by_id('p').send_keys('hhz0508+-')
	        browser.find_element_by_id('login_button').click()
	        time.sleep(2)
	        #打开留言板
	        writeLog()
	        while(True):
	            browser.get('https://user.qzone.qq.com/{}/334'.format(qq))
	            browser.switch_to.frame('tgb')
	            #点击批量管理
	            time.sleep(2)
	            mouse = browser.find_element_by_id('btnToSet')
	            ActionChains(browser).move_to_element(mouse).perform()
	            time.sleep(1)
	            browser.find_element_by_id('btnBatch').click()
	            browser.find_element_by_id('chkSelectAll').click()
	            browser.find_element_by_id('btnDeleteBatchBottom').click()
	            time.sleep(1)
	            browser.switch_to.parent_frame()
	            time.sleep(2)
	            browser.find_element_by_id('dialog_main_1').find_element_by_class_name('qz_dialog_layer_op').find_element_by_class_name('qz_dialog_layer_sub').click()
	            time.sleep(2)
	    except:
	        print("failure2")
	        print(traceback.format_exc())
	        writeLog()
	
	
	
	
	
	# 写错误日志并截图
	def writeLog():
	    # 组合日志文件名（当前文件名+当前时间）.比如：case_login_success_20150817192533
	    basename = os.path.splitext(os.path.basename(__file__))[0]
	    logFile = "log/"+basename + "-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + ".log"
	    logging.basicConfig(filename=logFile)
	    s = traceback.format_exc()
	    logging.error(s)
	    browser.get_screenshot_as_file("./" + logFile + "-screenshot_error.png")
	
	
	if __name__ == "__main__":
	    chrome_options = Options()
	    #chrome_options.add_argument('--headless')
	    chrome_options.add_argument('--disable-gpu')
	    chrome_options.add_argument('--no-sandbox')
	    browser = webdriver.Chrome(options=chrome_options)  # Chrome界面
	    # browser = webdriver.PhantomJS()  # 无界面
	    work(browser)
	    browser.quit()
```
