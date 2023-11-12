#!/usr/bin/python
# -*- coding:utf-8 -*-

from codecs import charmap_encode
from operator import index, itemgetter
from turtle import down
from typing import Container
import requests  # 用来抓取网页的html源码
import random  # 取随机数
from bs4 import BeautifulSoup  # 用于代替正则式 取源码中相应标签中的内容
import time  # 时间相关操作
import os
from rich.progress import track as tqdm
from utils import *
import zipfile
import shutil
import numpy as np
import argparse
import re
import pickle
from PIL import Image
import time

def parse_args():
    """Parse input arguments."""
    parser = argparse.ArgumentParser(description='config')
    parser.add_argument('--book_no', default='0000', type=str)
    parser.add_argument('--volume_no', default='1', type=int)
    parser.add_argument('--no_input', default=False, type=bool)
    args = parser.parse_args()
    return args


class Editer(object):
    def __init__(self, root_path, head='www.bilinovel', book_no='0000', volume_no=1):
        
        # 设置headers是为了模拟浏览器访问 否则的话可能会被拒绝 可通过浏览器获取，这里不用修改
        self.header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.67 Safari/537.36 Edg/87.0.664.47', 'referer': "https://w.linovelib.com/"}

        self.head = head
        self.main_page = f'https://www.bilinovel.com/novel/{book_no}.html'
        self.cata_page = f'https://www.bilinovel.com/novel/{book_no}/catalog'
        self.url_head = 'https://www.bilinovel.com'

        main_html = self.get_html(self.main_page)
        bf = BeautifulSoup(main_html, 'html.parser')
        bf = bf.find('div', {'id': 'bookDetailWrapper'})
        self.title = bf.find('h2', {"class": "book-title"}).text
        self.author = bf.find('a').text

        self.img_url_map = dict()###img_url_name:(img_url, epub_no)
        self.volume_no = volume_no

        self.epub_path = root_path
        self.temp_path = os.path.join(self.epub_path,  'temp_'+ self.title + '_' + str(self.volume_no))
        os.makedirs(self.temp_path, exist_ok=True)

        self.text_path = os.path.join(self.temp_path, 'OEBPS/Text')
        os.makedirs(self.text_path, exist_ok=True)

        self.img_path = os.path.join(self.temp_path,  'OEBPS/Images')
        os.makedirs(self.img_path, exist_ok=True)

        

    """
    获取html文档内容
    """
    def get_html(self, url, is_gbk=False):
        while True:
            try:
                req = requests.get(url=url, headers=self.header, timeout=5)
                if is_gbk:
                    req.encoding = 'GBK'       #这里是网页的编码转换，根据网页的实际需要进行修改，经测试这个编码没有问题
                break
            except Exception as e:
                print('3', e)
                time.sleep(random.choice(range(5, 10)))
        return req.text
    
    def get_html_img(self, url):
        while True:
            try:
                req=requests.get(url, headers=self.header, timeout=5)
                break
            except Exception as e:
                # print('3', e)
                pass
        return req.content
    
    def get_index_url(self):
        cata_html = self.get_html(self.cata_page, is_gbk=False)
        cata_html = restore_chars(cata_html)
        bf = BeautifulSoup(cata_html, 'html.parser')
        chap_html_list = bf.find('ol', {'id': 'volumes'}).find_all('li')
        volume = {}
        volume_array = 0
        name = ''
        img_url = ''
        chap_urls = []
        chap_names = []
        for chap_html in chap_html_list:
            if str(chap_html).startswith('<li class="chapter-bar chapter-li">'):
                volume_array += 1
                if volume_array==self.volume_no:
                    name = chap_html.text
            elif volume_array==self.volume_no:
                if str(chap_html).startswith('<li class="chapter-li jsChapter">'):
                    url = self.url_head + chap_html.find('a').get('href')
                    if chap_html.text == '插图':
                        img_url = url
                    else:
                        chap_names.append(chap_html.text)
                        chap_urls.append(url)
        volume = {'name': name, 'chap_names': chap_names, 'chap_urls':chap_urls, 'img_url': img_url}
        return volume
        
    def get_page_text(self, content_html, is_color=False):
        bf = BeautifulSoup(content_html, 'html.parser')
        text_with_head = bf.find('div', {'id': 'ccacontent', 'class': 'bcontent'}) 
        text_html = str(text_with_head)
        img_urlre_list = re.findall(r"<img .*?>", text_html)
        # print(img_urlre_list)
        for img_urlre in img_urlre_list:
            img_url_full = re.search(r'.[a-zA-Z]{3}/(.*?).(jpg|png)', img_urlre)
            img_url_name = img_url_full.group(1)
            img_url_tail = img_url_full.group(0)[-3:]
            img_url = f'https://img3.readpai.com/{img_url_name}.{img_url_tail}'

            text_html = text_html.replace('<br/>\n' + img_urlre +'\n<br/>', img_urlre)
            if not img_url in self.img_url_map:
                self.img_url_map[img_url] = str(len(self.img_url_map)).zfill(2)
            img_symbol = f'<p>[img:{self.img_url_map[img_url]}]</p>'
            # print(img_symbol)
            if '00' in img_symbol:
                text_html = text_html.replace(img_urlre, '')  #默认第一张为封面图片 不写入彩页
            else:
                text_html = text_html.replace(img_urlre, img_symbol)
                symbol_index = text_html.index(img_symbol)
                if text_html[symbol_index-1] != '\n':
                    text_html = text_html[:symbol_index] + '\n' + text_html[symbol_index:]
        text = BeautifulSoup(text_html, 'html.parser').get_text()
        text = restore_chars(text)
        return text
    
    def get_chap_text(self, url, chap_name, is_color=False):
        chap_no = url.split('/')[-1].strip('.html')
        text_chap = ''
        page_no = 0 
        while chap_no in url:
            if page_no == 0:
                str_out = chap_name
            else:
                str_out = f'    正在下载第{page_no + 1}页......'
            print(str_out)
            content_html = self.get_html(url, is_gbk=False)
            text = self.get_page_text(content_html, is_color=is_color)
            text_chap += text
            url = self.url_head + re.search(r'nextpage="(.*?)"', content_html).group(1)
            page_no += 1
        return text_chap
        
    
    def get_text(self, volume):
        print('****************************')
        img_url = volume['img_url']
        img_strs, del_index = [], []
        img_chap_name = '彩插'
        if img_url != '':
            text = self.get_chap_text(img_url, '彩页', True)
            text_html_color = text2htmls(img_chap_name, text)
            
        chap_names, chap_urls = volume['chap_names'], volume['chap_urls']
        for chap_no, (chap_name, chap_url) in enumerate(zip(chap_names, chap_urls)):
            # print(chap_name, end='   ')
            text = self.get_chap_text(chap_url, chap_name)
            text_html = text2htmls(chap_name, text) 
            textfile = self.text_path + f'/{str(chap_no).zfill(2)}.xhtml'
            with open(textfile, 'w+', encoding='utf-8') as f:
                f.writelines(text_html)
            for text_line in text_html:
                img_str = re.search(r"<img(.*?)\/>", text_line)
                if img_str is not None:
                    img_strs.append(img_str.group(0))

        print('****************************')
        
        # 将彩页中后文已经出现的图片删除，避免重复
        if img_url!='': #判断彩页是否存在
            text_html_color_new = []
            textfile = self.text_path + '/color.xhtml'
            for text_line in text_html_color: 
                is_save = True
                for img_str in img_strs:
                    if img_str in text_line:
                        is_save = False
                        break
                if is_save:
                   text_html_color_new.append(text_line) 
        
            with open(textfile, 'w+', encoding='utf-8') as f:
                f.writelines(text_html_color_new)

    def buffer(self, volume):
        filename = 'buffer.pkl'
        filepath = os.path.join(self.temp_path, filename)
        if os.path.isfile(filepath):
            with open(filepath, 'rb') as f:
                volume, self.img_url_map = pickle.load(f)
        else:
            with open(filepath, 'wb') as f:
                pickle.dump((volume ,self.img_url_map), f)
        return volume
    
    def is_buffer(self):
        filename = 'buffer.pkl'
        filepath = os.path.join(self.temp_path, filename)
        return os.path.isfile(filepath)

    def get_image(self, is_gui=False, signal=None):
        img_path = self.img_path
        if is_gui:
            len_iter = len(self.img_url_map.items())
            signal.emit('start')
            for i, (img_url, img_name) in enumerate(self.img_url_map.items()):
                content = self.get_html_img(img_url)
                with open(img_path+f'/{img_name}.jpg', 'wb') as f:
                    f.write(content) #写入二进制内容 
                signal.emit(int(100*(i+1)/len_iter))
            signal.emit('end')
        else:
            for img_url, img_name in tqdm(self.img_url_map.items()):
                content = self.get_html_img(img_url)
                with open(img_path+f'/{img_name}.jpg', 'wb') as f:
                    f.write(content) #写入二进制内容

    def get_cover(self, is_gui=False, signal=None):
        textfile = os.path.join(self.text_path, 'cover.xhtml')
        img_w, img_h = 300, 300
        try:
            imgfile = os.path.join(self.img_path, '00.jpg')
            img = Image.open(imgfile)
            img_w, img_h = img.size
            if is_gui:
                signal.emit(imgfile)
        except Exception as e:
            print(e)
            print('没有封面图片，请自行用第三方EPUB编辑器手动添加封面')
        img_htmls = get_cover_html(img_w, img_h)
        with open(textfile, 'w+', encoding='utf-8') as f:
            f.writelines(img_htmls)

    def get_toc(self, volume):
        toc_htmls = get_toc_html(self.title, volume["chap_names"])
        textfile = self.temp_path + '/OEBPS/toc.ncx'
        with open(textfile, 'w+', encoding='utf-8') as f:
            f.writelines(toc_htmls)

    def get_content(self, volume):
        num_chap = len(volume["chap_names"])
        num_img = len(os.listdir(self.img_path))
        content_htmls = get_content_html(self.title + '-' + volume['name'], self.author, num_chap, num_img, volume)
        textfile = self.temp_path + '/OEBPS/content.opf'
        with open(textfile, 'w+', encoding='utf-8') as f:
            f.writelines(content_htmls)

    def get_epub_head(self):
        mimetype = 'application/epub+zip'
        mimetypefile = self.temp_path + '/mimetype'
        with open(mimetypefile, 'w+', encoding='utf-8') as f:
            f.write(mimetype)
        metainf_folder = os.path.join(self.temp_path, 'META-INF')
        os.makedirs(metainf_folder, exist_ok=True)
        container = metainf_folder + '/container.xml'
        container_htmls = get_container_html()
        with open(container, 'w+', encoding='utf-8') as f:
            f.writelines(container_htmls)

    def get_epub(self, volume):
        os.remove(os.path.join(self.temp_path, 'buffer.pkl'))
        epub_file = self.epub_path + '/' + self.title + '-' + volume['name'] + '.epub'
        with zipfile.ZipFile(epub_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(self.temp_path):
                fpath = dirpath.replace(self.temp_path,'') #这一句很重要，不replace的话，就从根目录开始复制
                fpath = fpath and fpath + os.sep or ''
                for filename in filenames:
                    zf.write(os.path.join(dirpath, filename), fpath+filename)
        shutil.rmtree(self.temp_path)
        return epub_file
    
    def check_volume(self, volume, is_gui=False, flag=None, signal=None, editline=None):
        error_nos = []
        if 'javascript' in volume['img_url'] or 'cid' in volume['img_url']:
            error_msg = f'章节\"插图\"连接有误，请手动输入该章节链接(手机版“{self.head}”开头的链接):'
            if is_gui:
                print(error_msg)
                self.hang_flag = True
                signal.emit('hang')
                while self.hang_flag:
                    time.sleep(1)
                volume['img_url'] = editline.text() 
            else:
                volume['img_url'] = input(error_msg)

        for url_no, url in enumerate(volume['chap_urls']):
            if 'javascript' in url or 'cid' in url:
                error_nos.append(url_no)
        chap_names = volume['chap_names']
        for url_no in error_nos:
            error_msg = f'章节\"{chap_names[url_no]}\"连接有误，请手动输入该章节链接(手机版“{self.head}”开头的链接):'
            if is_gui:
                print(error_msg)
                self.hang_flag = True
                signal.emit('hang')
                while self.hang_flag:
                    time.sleep(1)
                volume['chap_urls'][url_no] = editline.text() 
            else:
                volume['chap_urls'][url_no] = input(error_msg)
        return volume

if __name__=='__main__':
    args = parse_args()
    download_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    # if not args.no_input:
    #     args.book_no = input('请输入书籍号：')
    #     args.volume_no = int(input('请输入卷号：'))
    
    args.book_no = 2342
    args.volume_no = 14

    
    editer = Editer(root_path='out', book_no=args.book_no, volume_no=args.volume_no)

    print('正在获取书籍信息....')
    volume = editer.get_index_url()
    print(editer.title + '-' + volume['name'], editer.author)
    print('****************************')
    if not editer.is_buffer():
        print('正在下载文本....')
        volume = editer.check_volume(volume)
        editer.get_text(volume)
        editer.buffer(volume)
    else:
        print('检测到文本文件，直接下载插图')
        volume = editer.buffer(volume)

    print('正在下载插图....')
    editer.get_image()
    
    print('正在编辑元数据....')
    editer.get_cover()
    editer.get_toc(volume)
    editer.get_content(volume)
    editer.get_epub_head()

    print('正在生成电子书....')
    epub_file = editer.get_epub(volume)
    print('生成成功！', f'电子书路径【{epub_file}】')
    
