def save_data(count):
    pause_on = self.env.checkBox_pause_seg.isChecked()

    if pause_on:
        self.pause.emit(True)   # 저장 시작
    try:
        sleep(3)

        for i in range(count):
            MSO.write(":ACQuire:SEGMented:INDex " + str(i + 1))
            datas = []
            for channel in channels:
                MSO.write(":WAVEFORM:SOURCE " + channel)
                string = MSO.query(":WAVeform:DATA?")
                datas.append(string[10:].replace(" ", "").replace("\n", "").split(","))

            time_tt = MSO.query(":WAVeform:SEGMented:TTAG?")
            time = start_time + datetime.timedelta(seconds=float(time_tt))
            time = time.strftime("%y_%m_%d %H_%M_%S.%f")

            file_name = os.path.join(File_path, time + "trig")
            with open(file_name + ".csv", "w") as f:
                for channel in channels:
                    f.write(channel + ",")
                f.write("\n")
                for line in range(len(datas[0])):
                    for data in datas:
                        f.write(data[line] + ",")
                    f.write("\n")

        sleep(3)

    finally:
        if pause_on:
            self.pause.emit(False)  # 저장 끝(Stop 케이스도 여기서 무조건 실행)
