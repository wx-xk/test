import copy
import glob
import pickle
import re
from time import sleep
import datetime

import cv2
import numpy as np
import pandas as pd
from PyQt5 import uic
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QColorDialog, QMessageBox
import sys
import pyvisa as pv

from Source.task_factory import Task_Factory

'''
from mcculw import ul
from mcculw.enums import InterfaceType
from mcculw.device_info import DaqDeviceInfo
'''
import os
color = {"p_red" : "#ffb3ba" , "p_green" : "#baffc9","p_yellow" : "#ffffcc"}

MSO = None
Counter_port = 0
Use_counter = True
Test_name = "test_name"
File_path = ""
MSO_Delay = 0.1


class Worker(QThread):
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    open_mso = pyqtSignal()
    pause = pyqtSignal(bool)
    def __init__(self, env):
        super().__init__()
        self.running = False
        self.env = env
        self.mode = "trigger"

    def get_scale(self):
        text = self.env.comboBox_scale.currentText()
        value = float(re.sub("[^\d\.]", "", text))
        if "ns" in text:
            value *= 1e-9
        elif "us" in text:
            value *= 1e-6

        return value

    def run(self):
        if self.running:
            return
        if not MSO:
            self.open_mso.emit()
            return

        if self.mode == "trigger":
            self.trigger_mode()
        elif self.mode == "seg":
            self.seg_mode()

        self.finished.emit()
        self.running = False
        self.log.emit("Stop // 측정 종료")

    def seg_mode(self):
        global MSO

        def save_data(count):
            sleep(3)

            for i in range(count):
                MSO.write(":ACQuire:SEGMented:INDex " + str(i + 1))
                datas = []
                for channel in channels:
                    MSO.write(":WAVEFORM:SOURCE " + channel)
                    string = MSO.query(':WAVeform:DATA?')
                    datas.append(string[10:].replace(' ', '').replace('\n', '').split(','))

                time_tt = MSO.query(":WAVeform:SEGMented:TTAG?")
                time = start_time + datetime.timedelta(seconds=float(time_tt))
                time = time.strftime("%y_%m_%d %H_%M_%S.%f")

                file_name = os.path.join(File_path, time + "trig")

                with open(file_name + ".csv", 'w') as f:
                    for channel in channels:
                        f.write(channel)
                        f.write(',')
                    f.write('\n')
                    for line in range(len(datas[0])):
                        for data in datas:
                            f.write(data[line])
                            f.write(',')
                        f.write('\n')
            sleep(3)


        self.log.emit("Start // 측정 시작")
        self.running = True
        MSO.write(":TIMebase:SCALe " + str(self.get_scale()))
        MSO.write(":WAVeform:FORMat ASCii")
        MSO.write(":WAVeform:POINts 1000")
        MSO.write(":SAVE:WAVeform:FORMat CSV")


        if self.env.checkBox_or.isChecked():
            self.or_trigger()
        else:
            pass
        
        MSO.write(":ACQuire:MODE SEGMented")
        num_seg = 3
        MSO.write(":ACQuire:SEGMented:COUNt {num_seg}")   #원상복귀 - 세그먼트 저장 개수

        ter = MSO.query(":TER?")
        count = 0

        channels = []
        for i in range(4):
            try:
                if "1" in MSO.query(":STATus? CHAN" + str(i + 1)):
                    channels.append("CHAN" + str(i + 1))
            except:
                pass

        while self.running:
            try:
                #while MSO.query("RSTate?") != "SING":
                MSO.write(":SINGle")
                #sleep(0.1)
                
                start_time = None

                while True:
                    try:
                        count = MSO.query(":WAVeform:SEGMented:COUNt?")
                    except:
                        continue

                    if int(count) > 1 and start_time is None:
                        start_time = datetime.datetime.now()
                    elif start_time is not None:
                        if datetime.datetime.now() - start_time > datetime.timedelta(minutes=30):
                            MSO.write(":STOP")
                            break

                    sleep(0.1)
                    if not self.running:
                        count_2 = MSO.query(":WAVeform:SEGMented:COUNt?")
                        count_2 = int(count_2)
                        if count_2 == 0:
                            break
                        self.pause.emit(True)
                        print("pause")
                        MSO.write(":STOP")
                        self.log.emit("데이터 저장중... 작업 금지")
                        save_data(count_2)
                        self.pause.emit(False)
                        print("resume")
                        self.log.emit("데이터 저장 완료")
                        break
                    if str(num_seg) in count:
                        break
                if not self.running:
                    break
            except Exception as e:
                print(str(e))

            count = MSO.query(":WAVeform:SEGMented:COUNt?")
            save_data(int(count))

    


    def or_trigger(self):

        global MSO
        
        channel1_type = self.env.comboBox_type1.currentText()    
        channel2_type = self.env.comboBox_type2.currentText()
        channel3_type = self.env.comboBox_type3.currentText() 
        channel4_type = self.env.comboBox_type4.currentText() 
        channel_type = channel1_type + channel2_type + channel3_type + channel4_type
        channel_type_analog = channel_type+"X"*16
        channel = [1,2,3,4]
        level_list = {
            1 : self.env.lineEdit_level1.text(),
            2 : self.env.lineEdit_level2.text(),
            3 : self.env.lineEdit_level3.text(),
            4 : self.env.lineEdit_level4.text(),
        }
        
        

        try:
            MSO.write("TRIGger:MODE OR")
            
            MSO.write(f':TRIGger:OR "{channel_type_analog}"')

            for i, ch in enumerate(channel):
                if channel_type[i] == "X":
                    continue
                level = float(level_list[ch])
                MSO.write(f":TRIGger:EDGE:LEVel {level},CHANnel{ch}")
        except Exception as e:
            self.log("OR trigger set failed"+ str(e))


       


    def trigger_mode(self):
        global MSO, Counter_port

        self.log.emit("Start // 측정 시작")
        self.running = True
        MSO.write(":ACQuire:MODE RTIMe")
        MSO.write(":TIMebase:SCALe "+str(self.get_scale()))
        MSO.write(":WAVeform:FORMat ASCii")
        MSO.write(":WAVeform:POINts 1000")
        MSO.write(":SAVE:WAVeform:FORMat CSV")

        if self.env.checkBox_or.isChecked():
            self.or_trigger()
        else:
            MSO.write(":TRIGger:MODE EDGE")


        ter = MSO.query(":TER?")
        count = 0

        channels = []
        for i in range(4):
            try:
                if "1" in MSO.query(":STATus? CHAN" +str(i+1)):
                    channels.append("CHAN"+str(i+1))
            except:
                pass

        while self.running:
            try:
                MSO.write(":SINGle")
                sleep(MSO_Delay)

                ter = MSO.query(":TER?")
                while "0" in ter:
                    ter = MSO.query(":TER?")
                    sleep(0.0001)
                    if not self.running:
                        break
                if not self.running:
                    break
            except Exception as ex:
                self.log.emit("1"+str(ex))
            try:
                time = datetime.datetime.now().strftime('%d %H_%M_%S.%f ')
                file_name = os.path.join(File_path, time+"trig" + str(count))

                datas = []
                for channel in channels:
                    MSO.write(":WAVEFORM:SOURCE "+channel)
                    string = MSO.query(':WAVeform:DATA?')
                    datas.append(string[10:].replace(' ', '').replace('\n', '').split(','))

                count += 1
                '''
                if Use_counter:
                    this_count = ul.c_in_32(0, Counter_port)
                    file_name += ", counter" + str(this_count)
                '''
                with open(file_name+".csv", 'w') as f:
                    for channel in channels:
                        f.write(channel)
                        f.write(',')
                    f.write('\n')
                    for line in range(len(datas[0])):
                        for data in datas:
                            f.write(data[line])
                            f.write(',')
                        f.write('\n')

                for _ in range(10000):
                    ter = MSO.query(":TER?")
                    sleep(0.0001)
                    if "0" in ter:
                        break
                    if not self.running:
                        break
                if not self.running:
                    break

            except Exception as ex:
                self.log.emit("2"+str(ex))
            if not self.running:
                break
        '''
        if Use_counter:
            this_count = ul.c_in_32(0, Counter_port)
            with open(os.path.join(File_path, "final_report" + str(this_count)) + ".log", 'w') as f:
                f.write("last count : "+ str(this_count))
        '''

    def stop(self):
        self.running = False

form = uic.loadUiType(r'resource/ui.ui')[0]

class GUI(QMainWindow, form):
    error_message = pyqtSignal(str)
    def __init__(self, env=None):
        super().__init__()
        self.env = env
        self.setupUi(self)
        self.toolButton_save.clicked.connect(self.set_save_location)
        self.pushButton_check.clicked.connect(self.check_freq)
        self.pushButton_start.clicked.connect(self.run_test)
        self.pushButton_start_seg.clicked.connect(self.run_seg)
        self.refresh_devices()

        self.toolButton_refresh.clicked.connect(self.refresh_devices)
        #self.comboBox_device.textActivated.connect(self.set_device)
        #self.comboBox_device.currentTextChanged.connect(self.set_device)
        self.pushButton_Connect.clicked.connect(self.set_device)
        self.worker = Worker(self)
        self.worker.progress.connect(self.reportProgress)
        self.worker.open_mso.connect(self.on_worker_open_mso)
        self.worker.log.connect(self.log)

        def puase(on_off):
            if on_off:
                print("pause")
            else:
                print("resume")

        self.worker.pause.connect(puase)



        self.error_message.connect(self.error_message_dialog)

        def debug_button():
            self.set_pulse_device()
        self.actionDebug.triggered.connect(debug_button)

        self.doubleSpinBox_trigger.valueChanged.connect(self.change_trigger_voltage)
        self.comboBox_ch.currentIndexChanged.connect(self.change_trigger_channel)
        self.comboBox_edge.currentTextChanged.connect(self.change_trigger_edge)

        self.pushButton_make_sensitive_map.clicked.connect(self.make_sensitive_map)
        self.pushButton_top_color_select.clicked.connect(self.top_color_select)
        self.pushButton_bottom_color_select.clicked.connect(self.bottom_color_select)
        self.pushButton_base_color_select.clicked.connect(self.base_color_select)
        self.checkBox_enable_gradiaent.stateChanged.connect(self.frame_gradient.setEnabled)

        self.checkBox_enable_gradiaent.setChecked(False)
        self.checkBox_enable_gradiaent.setChecked(True)


        def set_smap_image():
            file = QFileDialog.getOpenFileName(caption='Select image')
            if not file[0]:
                return
            self.lineEdit_smap_image.setText(file[0])
        self.pushButton_smap_image.clicked.connect(set_smap_image)

        def set_smap_qtpa():
            file = QFileDialog.getOpenFileName(caption='Select qtpa', filter='*.qtpa')
            if not file[0]:
                return
            self.lineEdit_smap_image_qtpa.setText(file[0])
        self.pushButton_smap_qtpa.clicked.connect(set_smap_qtpa)

        def set_smap_scan_log():
            file = QFileDialog.getExistingDirectory(caption='Select folder')
            if not file:
                return
            self.lineEdit_smap_scan_log.setText(file)
        self.pushButton_smap_scan_log.clicked.connect(set_smap_scan_log)

        def set_smap_mso_measures():
            file = QFileDialog.getExistingDirectory(caption='Select folder')
            if not file:
                return
            self.lineEdit_smap_mso_measures.setText(file)
        self.pushButton_smap_mso_measures.clicked.connect(set_smap_mso_measures)

        def set_smap_save_location():
            file = QFileDialog.getExistingDirectory(caption='Select folder')
            if not file:
                return
            self.lineEdit_smap_save_dir.setText(file)
        self.toolButton_smap_set_save.clicked.connect(set_smap_save_location)

        self.sensitive_map_thread = Task_Factory()

        self.smap_stop_flag = False

    #     self.pushButton_test.clicked.connect(self.test)
    
    # def test(self):
    #     global MSO
    #     r = MSO.query("RSTate?")
    #     print("RSTate",r)




    def log(self, string):
        self.textEdit_logbox.append(string)

    def error_message_dialog(self, string):
        QMessageBox.information(self, 'Error', string, QMessageBox.Ok)

    def run_seg(self):
        global File_path, Use_counter
        if self.worker.running:
            self.worker.stop()
            self.pushButton_start.setStyleSheet("")
            self.pushButton_start_seg.setStyleSheet("")
            return
        if not MSO:
            self.set_device()
        if not MSO:
            self.pushButton_start_seg.setStyleSheet("background-color: " + color["p_red"])
            return
        File_path = os.path.join(self.save_location(), self.test_name() + "_seg")
        os.mkdir(File_path)

        self.log("Saving at " + File_path)
        self.worker.mode = "seg"
        self.worker.start()
        self.pushButton_start_seg.setStyleSheet("background-color: " + color["p_green"])
        self.pushButton_start.setStyleSheet("background-color: " + color["p_yellow"])

    def run_test(self):
        global File_path, Use_counter, MSO_Delay
        if self.worker.running:
            self.worker.stop()
            self.pushButton_start.setStyleSheet("")
            self.pushButton_start_seg.setStyleSheet("")
            return
        if not MSO:
            self.set_device()
        if not MSO:
            self.pushButton_start.setStyleSheet("background-color: " + color["p_red"])
            return
        MSO_Delay = self.doubleSpinBox_delay.value()

        File_path = os.path.join(self.save_location(), self.test_name())
        os.mkdir(File_path)

        self.log("Saving at "+ File_path)
        self.worker.mode = "trigger"
        self.worker.start()
        self.pushButton_start.setStyleSheet("background-color: "+color["p_green"])
        self.pushButton_start_seg.setStyleSheet("background-color: " + color["p_yellow"])

    def change_trigger_voltage(self, value):
        if not MSO:
            self.log("To change value, connect Oscilloscope")
            self.log("오실로스코프를 연결 필요")
        try:
            MSO.write(":TRIGger:EDGE:LEVel " + str(value))
        except: pass

    def change_trigger_channel(self, value):
        if not MSO:
            self.log("To change value, connect Oscilloscope")
            self.log("오실로스코프를 연결 필요")
        try:
            MSO.write(":TRIGger:EDGE:SOURce CHANnel" + str(value+1))
        except: pass

    def change_trigger_edge(self, edge):
        if not MSO:
            self.log("To change value, connect Oscilloscope")
            self.log("오실로스코프를 연결 필요")
        try:
            if edge == "Fall":
                edge = "NEGative"
            elif edge == "Rise":
                edge = "POSitive"
            elif edge == "Both":
                edge = "EITHer"
            MSO.write(":TRIGger:EDGE:SLOPe " + edge)
        except: pass

    def on_worker_open_mso(self):
        self.log("Opening MSO")
        self.set_device()
        if MSO:
            self.log("MSO Opened")
            self.worker.start()

    def set_device(self):
        global MSO
        try:
            rm = pv.ResourceManager("C:\\Windows\\System32\\agvisa32.dll")
        except:
            rm = pv.ResourceManager()
        if MSO:
          MSO.close()
        try:
            print(self.device())
            MSO = rm.open_resource(self.device())
            MSO.timeout = 5000
            idn = MSO.query('*IDN?')
            print(idn)
            if ("MSO" not in idn) and ("KEYSIGHT" not in idn):
                raise ValueError
            self.device_box_color(color["p_green"])

            self.log("connection succeed // 오실로스코프 연결 성공")
        except:
            MSO = None
            self.device_box_color(color["p_red"])
            self.log("connection failed // 오실로스코프 연결 실패")

        try:
            tv = float(MSO.query(":TRIGger:EDGE:LEVel?"))
            self.doubleSpinBox_trigger.setValue(tv)
            tr = int(MSO.query(":TRIGger:EDGE:SOURce?").replace("CHAN", ""))
            self.comboBox_ch.setCurrentIndex(tr - 1)
            sl = MSO.query(":TRIGger:EDGE:SLOPe?").replace("NEGative","Fall").replace("POSitive","Rise").replace("EITHer","Both")
            self.comboBox_edge.setCurrentText(sl)
            MSO.timeout = 5000
        except:
            self.log("오실로스코프 정보 임포트 실패")
    '''
    def set_pulse_device(self):
        global Counter_port
        try:
            ul.release_daq_device(0)
            Counters = ul.get_daq_device_inventory(InterfaceType.ANY)
            ul.create_daq_device(0, Counters[self.counter_device_index()])
            Counter_port = self.counter_port_index()
            ul.c_clear(0, Counter_port)
            self.log("카운터 연결 성공")
            return True
        except :
            self.log("카운터 연결 실패")
            return False
    
    def refresh_pulse_device(self):
        global Counters
        while self.comboBox_device_2.count():
            self.comboBox_device_2.removeItem(0)

        ul.ignore_instacal()
        Counters = ul.get_daq_device_inventory(InterfaceType.ANY)

        for l in Counters:
            self.comboBox_device_2.addItem(str(l))
    '''
    def counter_device_index(self):
        return self.comboBox_device_2.currentIndex()

    def counter_port_index(self):
        return self.comboBox_counter_port.currentIndex()


    def reportProgress(self, a):
        print(a)

    def device_box_color(self, c="#baffc9"):
        self.comboBox_device.setStyleSheet("background-color: " + c)

    def device(self):
        return self.comboBox_device.currentText()

    def refresh_devices(self):
        while self.comboBox_device.count():
            self.comboBox_device.removeItem(0)
        rm = pv.ResourceManager()
        for l in rm.list_resources():
            self.comboBox_device.addItem(l)

    def trigger_voltage(self):
        return self.doubleSpinBox_trigger.value()

    def trigger_channel(self):
        return str(self.comboBox_ch.currentIndex() + 1)

    def test_name(self):
        temp = self.lineEdit_name.text()
        if temp == "" or ("auto" in temp) or ("Auto" in temp):
            temp = datetime.datetime.now().strftime('%Y_%m_%d %H_%M_%S')

        return temp + "_" + self.comboBox_scale.currentText()

    def save_location(self):
        return self.lineEdit_save.text()

    def set_save_location(self):
        file = QFileDialog.getExistingDirectory(caption='Select folder')
        if not file:
            return
        self.lineEdit_save.setText(file)

    def check_freq(self):
        self.run_test()

    def closeEvent(self, event):
        self.worker.stop()

    def make_sensitive_map(self):
        if self.sensitive_map_thread.isRunning():
            self.smap_stop_flag = True
            return

        self.sensitive_map_thread.set_function(self.__make_sensitive_map)
        self.sensitive_map_thread.start()
        self.pushButton_make_sensitive_map.setText("Stop")

    def __make_sensitive_map(self):
        try:
            self._make_sensitive_map()
        except Exception as e:
            self.error_message.emit(e.__str__())
            self.pushButton_make_sensitive_map.setText("Start")
            self.label_gen_status.setText(" ")

    def _make_sensitive_map(self):
        image_file = self.lineEdit_smap_image.text()
        if image_file == "":
            image_file = self.env.image_view.current_file_name
        qtpa = self.lineEdit_smap_image_qtpa.text()
        if qtpa == "":
            qtpa = image_file.replace(".png", ".qtpa")
        scan_log = self.lineEdit_smap_scan_log.text()
        base_image = cv2.imread(image_file)
        mso_measures = self.lineEdit_smap_mso_measures.text()

        scan_list = glob.glob(os.path.join(scan_log, "*.csv"))
        scan_list = [l for l in scan_list if "scan_log" not in l]

        save_dir = self.lineEdit_smap_save_dir.text()

        with open(qtpa, "rb") as f:
            qtpa_data = pickle.load(f)

        pts0 = np.array([[qtpa_data["point_x0"], qtpa_data["point_y0"]],
                         [qtpa_data["point_x1"], qtpa_data["point_y1"]],
                         [qtpa_data["point_x2"], qtpa_data["point_y2"]],
                         [qtpa_data["point_x3"], qtpa_data["point_y3"]], ]
                        , np.float32)

        pts1 = np.array([[qtpa_data["pixel_x0"], qtpa_data["pixel_y0"]],
                         [qtpa_data["pixel_x1"], qtpa_data["pixel_y1"]],
                         [qtpa_data["pixel_x2"], qtpa_data["pixel_y2"]],
                         [qtpa_data["pixel_x3"], qtpa_data["pixel_y3"]], ]
                        , np.float32)

        trans_loc_to_pix = cv2.getPerspectiveTransform(pts0, pts1)

        min_mode = not self.checkBox_use_max_peak.isChecked()
        grayscale_mode = self.checkBox_grayscale_image.isChecked()

        channel = "CHAN"+str(self.comboBox_ch.currentIndex() + 1)

        bottom_color = self.get_bottom_color("BGR")
        top_color = self.get_top_color("BGR")
        base_color = self.get_base_color("BGR")

        two_color_gradient = self.checkBox_enable_gradiaent.isChecked() and not self.checkBox_three_color_gradient.isChecked()
        three_color_gradient = self.checkBox_three_color_gradient.isChecked()

        x_shift = int(self.lineEdit_smap_shift_x.text())
        y_shift = int(self.lineEdit_smap_shift_y.text())
        grid_top = float(self.lineEdit_smap_top_voltage.text())
        grid_min = float(self.lineEdit_smap_bottom_voltage.text())

        def get_gradient_color(val):
            if two_color_gradient:
                result_color = top_color * val + bottom_color * (1 - val)
            elif three_color_gradient:
                if val < 0.5:
                    val = val * 2
                    result_color = base_color * val + bottom_color * (1 - val)
                else:
                    val = (val - 0.5) * 2
                    result_color = top_color * val + base_color * (1 - val)
            else:
                result_color = base_color
            return result_color

        colors = np.array([get_gradient_color(i / len(scan_list)) for i in range(len(scan_list))])
        energys = []
        total_counts = []

        errors = glob.glob(os.path.join(mso_measures, "*.csv"))
        errors.sort()

        overlap_image = copy.deepcopy(base_image)

        if grayscale_mode:
            overlap_image = cv2.cvtColor(overlap_image, cv2.COLOR_BGR2GRAY)
            overlap_image = cv2.cvtColor(overlap_image, cv2.COLOR_GRAY2BGR)


        for laser_current_file, overlap_color, index in zip(scan_list[::-1], colors[::-1], range(len(scan_list))):

            this_image = copy.deepcopy(base_image)

            if grayscale_mode:
                this_image = cv2.cvtColor(this_image, cv2.COLOR_BGR2GRAY)
                this_image = cv2.cvtColor(this_image, cv2.COLOR_GRAY2BGR)

            this_errors = copy.deepcopy(errors)
            laser_log = pd.read_csv(laser_current_file, skiprows=2, names=["X", "Y", "Time", "Laser", ""])
            laser_log["Time"] = pd.to_datetime(laser_log["Time"], format="%d %H:%M:%S.%f")

            min_time = laser_log["Time"].min()
            max_time = laser_log["Time"].max()

            this_errors = [file for file in this_errors if
                      min_time < datetime.datetime.strptime(os.path.basename(file).split(" trig")[0],
                                                            "%d %H_%M_%S.%f") < max_time]

            with open(laser_current_file) as f:
                first_line = f.readline()

            energy = float(first_line[first_line.find("energy : ") + 9:].replace(" ", "\n").split("\n")[0])
            energys.append(energy)
            total_counts.append(len(this_errors))

            # pixel size apply
            if self.checkBox_smap_pix_auto.isChecked():
                step_size = float(first_line[first_line.find("spacing : ") + 10:].replace(" ", "\n").split("\n")[0])
                result = trans_loc_to_pix @ [step_size, step_size, 1]
                pix_x_ = round(result[0] / result[2])
                pix_y_ = round(result[1] / result[2])
                result = trans_loc_to_pix @ [0, 0, 1]
                pix_x = round(result[0] / result[2])
                pix_y = round(result[1] / result[2])
                mean_size = (abs(pix_x - pix_x_) + abs(pix_y - pix_y_))/2
                pix_size = int(mean_size)
                print("auto pix size is : ", pix_size+1)
            else:
                pix_size = int(self.lineEdit_smap_pixel_size.text()) - 1

            pix_size_pos = int(pix_size / 2)
            pix_size_neg = int(pix_size / 2)

            if pix_size != pix_size_pos + pix_size_neg:
                pix_size_neg += 1

            pix_size_neg += 1

            # start of image generation loop
            for file, index2 in zip(this_errors, range(len(this_errors))):

                self.label_gen_status.setText("running... " + format((index / len(scan_list) + index2 / len(scan_list)/ len(this_errors))*100, ".1f") + "% ")
                err = os.path.basename(file).split(" trig")[0]
                time = datetime.datetime.strptime(err, "%d %H_%M_%S.%f")
                laser_log["dt"] = abs(laser_log["Time"] - time)
                if laser_log["dt"].min() > datetime.timedelta(milliseconds=500):
                    continue
                ser = laser_log.iloc[laser_log["dt"].argmin()]
                x = ser["X"]
                y = ser["Y"]
                result = trans_loc_to_pix @ [x, y, 1]
                pix_x = round(result[0] / result[2]) + x_shift
                pix_y = round(result[1] / result[2]) + y_shift
                # print(pix_x, pix_y,laser_log["dt"].min())
                df = pd.read_csv(file)
                if min_mode:
                    val = ((df[channel].min() - grid_min) / grid_top)
                else:
                    val = ((df[channel].max() - grid_min) / grid_top)

                if val > 1:
                    val = 1
                elif val < 0:
                    val = 0

                this_image[pix_y - pix_size_pos:pix_y + pix_size_neg, pix_x - pix_size_pos:pix_x + pix_size_neg] = get_gradient_color(val)
                overlap_image[pix_y - pix_size_pos:pix_y + pix_size_neg, pix_x - pix_size_pos:pix_x + pix_size_neg] = overlap_color

                if self.smap_stop_flag:
                    break

            if self.checkBox_enable_gradiaent.isChecked():
                y_10 = int(base_image.shape[0] / 10)
                y_20 = int(base_image.shape[0] * 2 / 10)

                for y in range(y_10, y_20):
                    val = 1 - (y - y_10) / y_10
                    this_image[y, y_10:y_10 + int(y_10 / 10)] = get_gradient_color(val)

                cv2.putText(this_image, "{}V".format(grid_top), [y_10 + int(y_10 / 10), y_10 + int(y_10 / 20)],
                            cv2.FONT_HERSHEY_PLAIN, int(y_10 / 100), tuple([int(x) for x in top_color]), 2)
                cv2.putText(this_image, "{}V".format(grid_min), [y_10 + int(y_10 / 10), y_20 + int(y_10 / 20)],
                            cv2.FONT_HERSHEY_PLAIN, int(y_10 / 100), tuple([int(x) for x in bottom_color]), 2)


            this_save_dir = os.path.join(save_dir, "sensitive_map_" + os.path.basename(mso_measures))
            if not os.path.exists(this_save_dir):
                os.makedirs(this_save_dir)
            this_save_dir = os.path.join(this_save_dir, os.path.basename(laser_current_file) + "_{0}nJ_count{1}".format(energy, len(this_errors)) + '.png')
            cv2.imwrite(this_save_dir,this_image)
            #self.set_progress(int((index + 1) / len(scan_list) * 100))

        this_save_dir_ = os.path.join(save_dir, "sensitive_map_" + os.path.basename(mso_measures))
        this_save_dir = os.path.join(this_save_dir_, "overlap.png")
        cv2.imwrite(this_save_dir, overlap_image)

        df = pd.DataFrame()
        df["energy"] = energys
        df["errors"] = total_counts
        df.to_csv(os.path.join(this_save_dir_, "summary.csv"))

        self.pushButton_make_sensitive_map.setText("Start")
        self.label_gen_status.setText(" ")

    def set_progress(self, val):
        self.progressBar_smap.setValue(val)

    def get_base_color(self, mode="RGB"):
            if self.lineEdit_smap_base_R.text() == "":
                return None
            if mode =="RGB":
                return np.array([int(self.lineEdit_smap_base_R.text()), int(self.lineEdit_smap_base_G.text()), int(self.lineEdit_smap_base_B.text())])
            elif mode == "BGR":
                return np.array([int(self.lineEdit_smap_base_B.text()), int(self.lineEdit_smap_base_G.text()), int(self.lineEdit_smap_base_R.text())])
            else:
                return None

    def get_top_color(self, mode="RGB"):
        if self.lineEdit_smap_top_R.text() == "":
            return None
        if mode =="RGB":
            return np.array([int(self.lineEdit_smap_top_R.text()), int(self.lineEdit_smap_top_G.text()), int(self.lineEdit_smap_top_B.text())])
        elif mode == "BGR":
            return np.array([int(self.lineEdit_smap_top_B.text()), int(self.lineEdit_smap_top_G.text()), int(self.lineEdit_smap_top_R.text())])
        else:
            return None

    def get_bottom_color(self, mode="RGB"):
        if self.lineEdit_smap_bottom_R.text() == "":
            return None
        if mode =="RGB":
            return np.array([int(self.lineEdit_smap_bottom_R.text()), int(self.lineEdit_smap_bottom_G.text()), int(self.lineEdit_smap_bottom_B.text())])
        elif mode == "BGR":
            return np.array([int(self.lineEdit_smap_bottom_B.text()), int(self.lineEdit_smap_bottom_G.text()), int(self.lineEdit_smap_bottom_R.text())])
        else:
            return None

    def top_color_select(self):
        val = self.color_select()
        self.lineEdit_smap_top_R.setText(str(int(val[1:3], 16)))
        self.lineEdit_smap_top_G.setText(str(int(val[3:5], 16)))
        self.lineEdit_smap_top_B.setText(str(int(val[5:7], 16)))
        self.label_top_color.setStyleSheet("background-color: " + val)

    def bottom_color_select(self):
        val = self.color_select()
        self.lineEdit_smap_bottom_R.setText(str(int(val[1:3], 16)))
        self.lineEdit_smap_bottom_G.setText(str(int(val[3:5], 16)))
        self.lineEdit_smap_bottom_B.setText(str(int(val[5:7], 16)))
        self.label_bottom_color.setStyleSheet("background-color: " + val)

    def base_color_select(self):
        val = self.color_select()
        self.lineEdit_smap_base_R.setText(str(int(val[1:3], 16)))
        self.lineEdit_smap_base_G.setText(str(int(val[3:5], 16)))
        self.lineEdit_smap_base_B.setText(str(int(val[5:7], 16)))
        self.label_base_color.setStyleSheet("background-color: " + val)

    def color_select(self):
        color_dialog = QColorDialog()
        color_dialog.exec_()
        return color_dialog.selectedColor().name()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    myWindow = GUI()
    myWindow.show()
    app.exec_()
