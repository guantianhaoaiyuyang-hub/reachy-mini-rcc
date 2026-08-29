from doubao.audio import record, save_wav

audio = record(5)

save_wav(audio, "recordings/test_record.wav")

print("测试完成")