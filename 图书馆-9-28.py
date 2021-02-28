# -*- coding: utf8 -*-
import re
import os
import json
import smtplib
import logging
import requests
from threading import Thread
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
# 日志相关
logger = logging.getLogger()
logger.setLevel(logging.WARNING)


class Book(Thread):
    host = 'https://libreserve.sdust.edu.cn'
    state_dict = {
        1: '预约中',
        2: '已进入',
        3: '已离开',
        4: '已取消',
        5: '已失效'
    }

    def __init__(self, user, token, isContinue, email_adress):
        super(Book, self).__init__()
        self.user = user
        self.token = token
        self.email_adress = email_adress
        self.output_json = {}
        self.headers = {}
        self.output_json['user'] = self.user
        self.isContinue = isContinue
        self.headers['authorization'] = self.token
        self.can_order_type = [2]
        self.order_type_index = 0
        self.type_number = self.can_order_type[self.order_type_index]

    # 预定函数
    def run(self):
        # 核实状态
        self.check_state()
        if self.isContinue:
            self.cancel_recored()
        else:
            if self.state == '已进入':
                self.output_json['state'] = self.state
                self.output_json['msg'] = '您已进入{}'.format(self.seat_number)
                return
            elif self.state == '预约中':
                self.output_json['state'] = self.state
                self.output_json['msg'] = '您已预约{}'.format(self.seat_number)
                return 
        self.output_json['msg'] = self.order()
        self.output_json['state'] = self.state
        # 邮件通知
        if self.state == '续约成功':
            self.send_email('{}，续约状态: {}'.format(self.user, self.state), str(self.output_json))
        elif self.state == '预约成功':
            self.send_email('{}，抢到座位啦-{}'.format(self.user, self.seat_number), str(self.output_json))

    # 检查用户状态
    def check_state(self):
        url_history = '/api/homeapi/user/getMyOrderRecored?page=1&pageSize=15'
        r = requests.get(self.host + url_history, headers=self.headers)
        recent_recored = json.loads(r.text)['data'][0]
        status = recent_recored['status']
        self.state = self.state_dict[status]
        if status >= 4:  # 取消或失效
            # 改成send_email
            print('{}，未检测到预约信息，为您预约中...'.format(
                self.user))
        elif status == 1:  # 预约中
            self.seat_number = recent_recored['address']
        elif status == 2:  # 已进入
            self.seat_number = recent_recored['address']
            if (datetime.now()-datetime.strptime(recent_recored['enter_time'], r'%Y-%m-%d %H:%M:%S')).seconds / 1000 < 20:
                current_hour = datetime.now().hour
                if current_hour in [7, 8]:
                    self.send_email('{}，早上好，很高兴见到您'.format(self.user), '祝您心情舒畅，学习愉快~\n学习之余，记得喝水哦，多活动活动')
                elif current_hour in [13, 14]:
                    self.send_email('{}，下午好，老朋友，又见到您了'.format(self.user), '祝您心情舒畅，学习愉快~\n学习之余，记得喝水哦，多活动活动')
                elif current_hour in [18, 19, 20]:
                    self.send_email('{}，晚上好，坚持就是胜利！加油~'.format(self.user), '祝您心情舒畅，学习愉快~\n学习之余，记得喝水哦，多活动活动')
        elif recent_recored['status'] == 3:  # 已离开
            if (datetime.now() - datetime.strptime(recent_recored['leave_time'], r'%Y-%m-%d %H:%M:%S')).seconds / 1000 < 20:
                current_hour = datetime.now().hour
                if current_hour in [11, 12, 13]:
                    self.send_email('忙碌了一上午的{}，检测到您已离开图书馆'.format(self.user), '好好吃饭睡觉呀，抢座还是交给我吧，我在马不停蹄滴抢座中...')
                elif current_hour in [17, 18]:
                    self.send_email('学了了一下午了，{}，检测到您已离开图书馆'.format(self.user), '好好吃饭，抢座还是交给我吧，我在马不停蹄滴抢座中...')
                elif current_hour in [20, 21, 22, 23]:
                    self.send_email('夜深了，{}，注意保暖，明天再来哟~'.format(self.user), '回去好好睡觉，忙碌了一天了，我也该休息了，晚安，好梦，good night~')

    # 预定座位
    def order(self):
        url_get_seat = '/api/homeapi/user/userOrderRoom?type={}'.format(self.type_number)
        r = requests.get(self.host + url_get_seat, headers=self.headers)
        r.encoding = 'utf-8'
        data = json.loads(r.text)
        seat_number = re.findall('\d+', data['msg'])
        if '排队' in data['msg']:
            if self.order_type_index + 1 < len(self.can_order_type):
                self.type_number = self.can_order_type[self.order_type_index+1]
                return self.order()
            else:
                self.state = '续约失败' if self.isContinue else '预约失败'
                return '在抢了，在抢了，很快就会有的...'
        elif 'downloading' in data['msg'] or '重新预约' in data['msg']:
            return self.order()
        elif len(seat_number):
            self.state = '续约成功' if self.isContinue else '预约成功'
            print(self.state)
            self.seat_number = seat_number[0]
            return '预约成功-{}'.format(self.seat_number)

    # 取消预订
    def cancel_recored(self):
        url_cancel = '/api/homeapi/user/cancelRecored?type={}'.format(
            self.type_number,)
        r = requests.get(self.host + url_cancel, headers=self.headers)
        data = json.loads(r.text)
        return data['msg']

    # 发送邮箱信息
    def send_email(self, s, c):
        msg_Sender = '277611581@qq.com'  # 发送方邮箱
        # 发送方邮箱的授权码aoqgeoezwnmcbigb(小号) abmiysvgtsfjdicd(大号)
        msg_code = 'aoqgeoezwnmcbigb'
        if len(self.email_adress):
            msg_Receiver = self.email_adress  # 收件人邮箱
        else:
            self.output_json['email'] = '未提供邮箱信息'
            return

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
            self.output_json['email'] = True
        except Exception as e:
            self.output_json['email'] = False
        finally:
            s.quit()

    # 一言
    def get_hitokoto(self):
        r = requests.get(
            'https://international.v1.hitokoto.cn/', headers=self.headers)
        data = json.loads(r.text)
        return '{hitokoto}'.format(**data)


# 信息查询
def get_info():
    host = 'https://libreserve.sdust.edu.cn'
    url_get_info = '/api/homeapi/Index/getStatisticDataByType?type=2'
    r = requests.get(host + url_get_info)
    data = json.loads(r.text)['data']
    print('室内人数：{onRoomNum} | 预约人数：{orderNum} | 剩余座位：{canOrderNum} | 今日人流量：{todayTrfficNum}'.format(**data))
    # 获取等待用户数据
    url_get_wait = '/api/homeapi/Index/getWaitingUserList?&page=1&pageSize=15'
    r = requests.get(host + url_get_wait)
    data = json.loads(r.text)['data']
    print('当前等待: {}位'.format(len(data)))
    for user in data:
        print('姓名：{name} | 时间：{wait_minutes}'.format(**user))


def main(*args):
    # 判断运行状态
    isContinue = datetime.now().minute % 30 == 0 and datetime.now().second < 6
    # 输出关键信息
    try:
        get_info()
    except:
        print('[运行状态]: 获取信息失败')
    print('[运行模式]: ' + ('续约中...' if isContinue else '抢座中...'))
    # 创建线程
    all_user_threads_dict = {}
    test_dict = {'Polygon': 'bfd5b2201042a6508f8381a65b9f596b | 33699@outlook.com'}
    for key, value in test_dict.items():
        if re.match('[\w\d]{32}.*', value):
            if '|' in value:
                token, email_address = value.split(' | ')
            else:
                token = value
                email_address = ''
            all_user_threads_dict[key] = Book(
                key, token, isContinue, email_address)
    for user, book in all_user_threads_dict.items():
        book.start()
    for user, book in all_user_threads_dict.items():
        book.join()
    all_output_json = {}
    for user, book in all_user_threads_dict.items():
        print(book.output_json)
        all_output_json[user] = book.output_json
    return all_output_json
main()
