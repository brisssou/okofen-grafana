"""import os
import sys

path = os.path.dirname(__file__)

file_name = 'my_input_file.xml'

if __name__ == "__main__":
    with open(os.path.join(path, './' + file_name), 'r', encoding='cp1252') as f1:
        lines = f1.read()
        f2 = open(os.path.join(path, './' + 'my_output_file.xml'), 'w', encoding='utf-8')
        f2.write(lines)
        f2.close()
"""
import csv
from os import listdir
from os.path import isfile, join

datafiles = [
    join("data", f)
    for f in listdir("data")
    if isfile(join("data", f))
]

for datafile in datafiles:
    print(f"Reading {datafile}")
    with open(datafile, newline='', encoding='cp1252') as csvfile:
        datareader = csv.reader(csvfile, delimiter=',', quotechar='|')
        for row in datareader:
            print('||||'.join(row))

columns = {
    "Datum ": "Date",
    "Zeit ": "Time",
    "AT [°C]": "Outside Temp °C",
    "ATakt [°C]": "Outside Temp °C Current",
    "KT Ist [°C]": "Boiler Temp",
    "KT Soll [°C]": "Boiler Temp asked",
    "BR ": "Burner Contact",
    "Sperrzeit ": "Blocking time",
    "PE1_BR1 ": "Burner1  Contact",
    "HK1 VL Ist[°C]": "Circuit1 flow temp",
    "HK1 VL Soll[°C]": "Circuit1 flow temp asked",
    "HK1 RT Ist[°C]": "Circuit1 ambiant temp",
    "HK1 RT Soll[°C]": "Circuit1 ambiant temp asked",
    "HK1 Pumpe": "Circuit1 pump",
    "HK1 Mischer": "Circuit1 Water mix",
    "HK1 Fernb[°C]": "Circuit1 Thermostat",
    "HK1 Status": "Circuit1 status",
    "HK2 VL Ist[°C]": "Circuit2 flow temp",
    "HK2 VL Soll[°C]": "Circuit2 flow temp asked",
    "HK2 RT Ist[°C]": "Circuit2 ambiant temp",
    "HK2 RT Soll[°C]": "Circuit1 ambiant temp asked",
    "HK2 Pumpe": "Circuit2 pump",
    "HK2 Mischer": "Circuit2 Water mix",
    "HK2 Fernb[°C]": "Circuit2 Thermostat",
    "HK2 Status": "Circuit1 status",
    "Zubrp1 Pumpe": "Primary pump",
    "Radio 16499 Temp[°C]": "Temp Probe",
    "Radio 16499 Hum[%]": "Humidity Probe",
    "PE1 KT[°C]": "Boiler Temp",
    "PE1 KT_SOLL[°C]": "Boiler Temp asked",
    "PE1 UW Freigabe[°C]": "Release Temp",
    "PE1 Modulation[%]": "Modulation",
    "PE1 FRT Ist[°C]": "Flam Temp",
    "PE1 FRT Soll[°C]": "Flam Temp asked",
    "PE1 FRT End[°C]": "Flam Temp max",
    "PE1 Einschublaufzeit[zs]": "Burner fill duration",
    "PE1 Pausenzeit[zs]": "Pause duration",
    "PE1 Luefterdrehzahl[%]": "Burner Fan",
    "PE1 Saugzugdrehzahl[%]": "Smoke Fan",
    "PE1 Unterdruck Ist[EH]": "Pressure",
    "PE1 Unterdruck Soll[EH]": "Pressure asked",
    "PE1 Fuellstand[kg]": "Wood stock silo",
    "PE1 Fuellstand ZWB[kg]": "Wood stock local",
    "PE1 Status": "Status",
    "PE1 Statusbit": "Status bit",
    "PE1 Motor ES": "Burner motor screw",
    "PE1 Motor RA": "Extraction",
    "PE1 Motor RES1": "Reserve Motor 1",
    "PE1 Motor TURBINE": "Turbine",
    "PE1 Motor ZUEND": "Lighter",
    "PE1 Motor UW[%]": "Boiler Pump",
    "PE1 Motor AV": "Ashtray",
    "PE1 Motor RES2": "Reserve Motor 2",
    "PE1 Motor MA": "Electro valve",
    "PE1 Motor RM": "Chimney Swiping",
    "PE1 Motor SM": "Output relay failure",
    "PE1 CAP RA": "KAP RA",
    "PE1 CAP ZB": "KAP ZW",
    "PE1 AK": None,
    "PE1 Saug-Int[min]": "Suck Interval",
    "PE1 DigIn1": "DigIn1",
    "PE1 DigIn2": "DigIn2",
    "PE1 CntDig1": "Dig1 Counter",
    "PE1 Ashfill[kg]": "Ash Quantity",
    "PE1 Runtime[h]": "Runtime",
    "Fehler1 ": "Error 1",
    "Fehler2 ": "Error 2",
    "Fehler3 ": "Error 3",
}
