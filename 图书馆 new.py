# -*- coding: utf8 -*-
import re
import os
import json
import smtplib
import logging
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
logger = logging.getLogger()
logger.setLevel(logging.WARNING)


class Book(object):
    type_index = 0  # 类型索引
    success_user = []  # 成功用户
    isContinue = False  # 是否续约
    authorization_dict = {}  # 用户授权的authorization
    type_candidate_list = [2]
    headers = {'authorization': ''}
    host = 'https://libreserve.sdust.edu.cn'
    type_number = type_candidate_list[type_index]

    def __init__(self, *args):
        isContinue = datetime.now().minute % 30 == 0 and datetime.now().second < 15
        print('[运行模式]: ' + ('续约中...' if isContinue else '抢座中...'))
        for key, value in os.environ.items():
            if re.match('[\w\d]{32}', value):
                self.authorization_dict[key] = value
        self.authorization_dict = {'周建': 'bfd5b2201042a6508f8381a65b9f596b',
            '弭霄': '449ebf110b5e10c4bf1738fb88d09403'}
        # 信息查询
        url_get_info = '/api/homeapi/Index/getStatisticDataByType?type={}'.format(self.type_number)
        r = requests.get(self.host + url_get_info, headers=self.headers)
        data = json.loads(r.text)['data']
        print('室内人数：{onRoomNum} | 预约人数：{orderNum} | 剩余座位：{canOrderNum} | 今日人流量：{todayTrfficNum}'.format(**data))
        # 获取等待用户数据
        url_get_wait = '/api/homeapi/Index/getWaitingUserList?type={}&page=1&pageSize=15'.format(
            self.type_number)
        r = requests.get(self.host + url_get_wait, headers=self.headers)
        data = json.loads(r.text)['data']
        print('当前等待: {}位'.format(len(data)))
        for user in data:
            print('姓名：{name} | 时间：{wait_minutes}'.format(**user))
        print(self.book())

    # 预定座位
    def order(self, user):
        print('[运行状态]: 开始预定座位中...')
        self.headers['authorization'] = self.authorization_dict[user]
        url_get_seat = '/api/homeapi/user/userOrderRoom?type={}'.format(
            self.type_number)
        # type=2是阅览室 5是A区
        r = requests.get(self.host + url_get_seat, headers=self.headers)
        r.encoding = 'utf-8'
        data = json.loads(r.text)
        print('[运行状态]: {msg}'.format(**data))
        seat_number = re.findall('\d+', data['msg'])
        if '排队' in data['msg']:
            print('[运行状态]: 当前自习室人数过多，切换其他自习室中...')
            if self.type_index + 1 < len(self.type_candidate_list):
                self.type_number = self.type_candidate_list[self.type_index+1]
                return order(user)
            else:
                return '暂时没有空座位哦~'
        elif 'downloading' in data['msg']:
            return order(user)
        elif len(seat_number):
            self.success_user.append(user)
            return '预约成功-{}'.format(seat_number[0])
        else:
            return '您已预约-{}'.format(self.get_history()[1])

    # 查询用户预约历史
    def get_history(self):
        url_history = '/api/homeapi/user/getMyOrderRecored?page=1&pageSize=15'
        r = requests.get(self.host + url_history, headers=self.headers)
        history_data = json.loads(r.text)
        id_number = history_data['data'][0]['id']
        seat_number = history_data['data'][0]['address']
        return id_number, seat_number

    # 取消预订
    def cancel_recored(self, user):
        self.headers['authorization'] = self.authorization_dict[user]
        url_concel = '/api/homeapi/user/cancelRecored?type={}'.format(
            self.type_number)
        r = requests.get(self.host + url_concel, headers=self.headers)
        data = json.loads(r.text)
        print('[运行状态]: {msg}'.format(**data))
        return data['msg']

    # 发送邮箱信息
    def send_email(self, s, c):
        msg_Sender = '277611581@qq.com'  # 发送方邮箱
        # 发送方邮箱的授权码aoqgeoezwnmcbigb(小号) abmiysvgtsfjdicd(大号)
        msg_code = 'aoqgeoezwnmcbigb'
        msg_Receiver = '33699@outlook.com'  # 收件人邮箱

        subject = s  # 主题
        content = c  # 正文
        msg = MIMEText(content, 'plain', 'utf-8')

        msg['Subject'] = subject
        msg['From'] = msg_Sender
        msg['To'] = msg_Receiver
        try:
            s = smtplib.SMTP_SSL("smtp.qq.com", 465)  # 邮件服务器及端口号
            s.login(msg_Sender, msg_code)
            s.sendmail(msg_Sender, msg_Receiver, msg.as_string())
            print("[邮件状态]: 发送成功")
        except Exception as e:
            print("[邮件状态]: 发送失败")
        finally:
            s.quit()

    # 一言
    def get_hitokoto(self):
        r = requests.get('https://international.v1.hitokoto.cn/', headers=self.headers)
        data = json.loads(r.text)
        return '{hitokoto}\n\t\t\t\t————{from}'.format(**data)

    # 预定函数
    def book(self):
        output_str = ''
        for user in self.authorization_dict.keys():
            print('[当前用户]: ' + user)
            if self.isContinue:
                self.cancel_recored(user)
            order_msg = self.order(user)
            print(order_msg)
            output_str += (' | ' if len(output_str) else '')
            output_str += '{}: {}'.format(user, order_msg)
        output_email_str = output_str + '\n\n' + self.get_hitokoto()
        if len(self.success_user):
            if isContinue:
                if '成功' in output_str:
                    if len(self.success_user) == len(self.authorization_dict):
                        send_email('全部用户续约成功!', output_email_str)
                    else:
                        send_email('续约状态通知，{}/{}'.format(len(self.success_user),
                                                         len(self.authorization_dict)), output_email_str)
                else:
                    print('[运行状态]: 当前用户全部在馆')
            else:
                send_email('抢到座位啦~{}'.format(
                    '&'.join(self.success_user)), output_email_str)
        return output_str
    

Book()
