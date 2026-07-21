#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN  10
#define RST_PIN 9

MFRC522 rfid(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  // PCD_Init() only writes registers — it never reads one back, so it "succeeds"
  // even with the reader unplugged, and the sketch then sits in loop() detecting
  // nothing, silently. Read the version register so a bad SPI/power link is visible
  // at boot instead of looking like "no cards are being tapped".
  //
  // VersionReg is a hardware constant, so reading it repeatedly is a bus test: a
  // sound link returns the same value every time. Values that vary between reads
  // mean we are sampling noise, not a register — the failure mode that looks like
  // an intermittently working reader. Checking only for 0x00/0xFF misses it, since
  // noise is usually neither.
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  bool stable = true;
  for (byte i = 0; i < 8; i++) {
    if (rfid.PCD_ReadRegister(MFRC522::VersionReg) != v) stable = false;
  }
  Serial.print("RC522:0x");
  if (v < 0x10) Serial.print("0");
  Serial.print(v, HEX);
  if (v == 0x00 || v == 0xFF) Serial.println(" NO-COMMS");       // nothing answering
  else if (!stable)           Serial.println(" UNSTABLE-SPI");   // noise: check wiring
  else if (v == 0x91 || v == 0x92) Serial.println(" OK");        // genuine NXP
  else                        Serial.println(" OK-CLONE");       // consistent clone

  Serial.println("READY");
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  Serial.print("UID:");
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
    Serial.print(rfid.uid.uidByte[i], HEX);
  }
  Serial.println();

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  delay(1000);
}
