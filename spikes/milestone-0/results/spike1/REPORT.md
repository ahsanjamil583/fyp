# Spike 1 - TTS and Roman Urdu

Answers decision **D1**: which language route the voice channel should take.

## How to read this

Play each sample and judge two things: is it intelligible, and does it sound
like a person answering a phone. The similarity column is a proxy, not a verdict -
a high score with unnatural prosody is still a bad phone experience.

- Samples: **8** (4 Roman Urdu)
- Whisper round trip: **run**

## Round-trip content recall by engine

Scored on the tokens that matter on a sales call - product words and prices.
Grammar words are excluded, and a transcription returned in Urdu/Devanagari
script is not penalised as long as the product names and numbers survive.

| Engine | Renders | Mean content recall | Script shifts | Verdict |
|---|---|---|---|---|
| edge_en_us | 8 | 0.91 | 0 | usable |
| windows_sapi | 8 | 0.88 | 0 | usable |
| edge_ur_pk | 8 | 0.67 | 3 | poor |
| edge_en_in | 8 | 0.66 | 4 | poor |

## The question that matters

If Roman Urdu scores clearly worse than English on every engine, route (a) -
forcing English on the voice channel - is the safe choice for the demo.

- **Roman Urdu**: mean content recall 0.58 across 16 renders
- **English**: mean content recall 0.98 across 16 renders

## Samples

### Sample 1 (english, tenant: captured)

**Asked:** (stored sample)

**Reply:** We have the following products available: White Running Sneakers PKR 4,500. Black Formal Shoes PKR 5,000. Brown Leather Loafers PKR 6,200.

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample01_edge_en_us.mp3` | 1.7s | 1.08s | 1.0 | latin | We have the following products available, white running sneakers PKR 4 |
| edge_en_in | `sample01_edge_en_in.mp3` | 2.21s | 0.84s | 1.0 | latin | We have the following products available. White running sneakers PKR 4 |
| edge_ur_pk | `sample01_edge_ur_pk.mp3` | 2.4s | 0.91s | 0.938 | latin | We have the following products available. White running sneakers 4500. |
| windows_sapi | `sample01_sapi.wav` | 0.21s | 1.11s | 1.0 | latin | We have the following products available, white running sneakers PKR 4 |

### Sample 2 (english, tenant: captured)

**Asked:** (stored sample)

**Reply:** Yes, we have a variety of shoes. Would you like to know more about any of these?

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample02_edge_en_us.mp3` | 1.38s | 0.83s | 1.0 | latin | Yes, we have a variety of shoes. Would you like to know more about any |
| edge_en_in | `sample02_edge_en_in.mp3` | 2.36s | 0.85s | 1.0 | latin | Yes, we have a variety of shoes. Would you like to know more about any |
| edge_ur_pk | `sample02_edge_ur_pk.mp3` | 2.01s | 0.83s | 1.0 | latin | Yes, we have a variety of shoes. Would you like to know more about any |
| windows_sapi | `sample02_sapi.wav` | 0.13s | 1.19s | 1.0 | latin | Yes, we have a variety of shoes. Would you like to know more about any |

### Sample 3 (roman_urdu, tenant: captured)

**Asked:** (stored sample)

**Reply:** Ji, White Running Sneakers available hain. Qeemat PKR 4,500 hai.

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample03_edge_en_us.mp3` | 1.69s | 0.74s | 0.857 | latin | G. White running sneakers available Hain. Heimat PKR 4500 High. |
| edge_en_in | `sample03_edge_en_in.mp3` | 2.11s | 0.74s | 0.286 | urdu/devanagari | जी, वाइट रॉनिंग स्नीकर्स अवेलिबल है। कीमत PKR 4500 है। |
| edge_ur_pk | `sample03_edge_ur_pk.mp3` | 1.75s | 0.73s | 0.714 | latin | G. White running sneakers available high. 4500 high. |
| windows_sapi | `sample03_sapi.wav` | 0.17s | 1.89s | 0.857 | latin | White running sneakers available Hain Keymat PKR 4500 HI |

### Sample 4 (roman_urdu, tenant: captured)

**Asked:** (stored sample)

**Reply:** footwear hai: White Running Sneakers PKR 4,500, Black Formal Shoes PKR 5,000. kya chahiyeh?

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample04_edge_en_us.mp3` | 1.63s | 0.83s | 0.909 | latin | Footwear high, white running sneakers PKR 4500, black formal shoes PKR |
| edge_en_in | `sample04_edge_en_in.mp3` | 2.02s | 0.8s | 0.909 | urdu/devanagari | Footwear है, White Running Sneakers PKR 4500, Black Formal Shoes PKR 5 |
| edge_ur_pk | `sample04_edge_ur_pk.mp3` | 1.99s | 0.85s | 0.182 | urdu/devanagari | फुट्वर हाई, वाइट रानिंग स्नीकर्स 4500, ब्लेक फोर्मल शूस 5000, किया. |
| windows_sapi | `sample04_sapi.wav` | 0.15s | 1.14s | 0.909 | latin | Footwear High, White Running Sneakers PKR 4500, Black Formal Shoes PKR |

### Sample 5 (roman_urdu, tenant: captured)

**Asked:** (stored sample)

**Reply:** Maine Grey Tracksuit find kar liya hai aur quantity 2 ka draft tayar kar diya hai. Aap neeche draft confirm kar sakte hain.

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample05_edge_en_us.mp3` | 2.03s | 0.86s | 0.7 | latin | Main grey tracksuit find car lia high or quantity 2 ca draft tire car  |
| edge_en_in | `sample05_edge_en_in.mp3` | 1.77s | 0.9s | 0.0 | urdu/devanagari | मैंने ग्रेट राक सूट फाइन कर लिया है और क्वांटिटी तुका ड्राफ्ट तैयार कर |
| edge_ur_pk | `sample05_edge_ur_pk.mp3` | 1.99s | 0.82s | 0.5 | urdu/devanagari | Main Gray Treksuit Find Car High A or Quantity 2 का Draft Car D.H. AP  |
| windows_sapi | `sample05_sapi.wav` | 0.11s | 1.31s | 0.7 | latin | Main grey tracksuit find car lia high or quantity 2K Draft Tyre car di |

### Sample 6 (roman_urdu, tenant: captured)

**Asked:** (stored sample)

**Reply:** Grey Tracksuit ki price PKR 4,800 hai.

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample06_edge_en_us.mp3` | 1.45s | 0.89s | 0.8 | latin | Gray tracksuit key price PKR 4800 high. |
| edge_en_in | `sample06_edge_en_in.mp3` | 1.59s | 5.12s | 0.2 | urdu/devanagari | ग्रेट रैक सूट की प्राइस P.K.R. 4,800 है। |
| edge_ur_pk | `sample06_edge_ur_pk.mp3` | 1.21s | 0.7s | 0.2 | urdu/devanagari | ग्रे ट्रेक्सूट की प्राइस 4800 हाई |
| windows_sapi | `sample06_sapi.wav` | 0.07s | 5.21s | 0.6 | latin | Gray track suit key price PKR 4800 high |

### Sample 7 (english, tenant: captured)

**Asked:** (stored sample)

**Reply:** This is a Fashion business, so pizza is not available here. You can ask about shirts, hoodies, shoes, jeans, sizes, or colors.

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample07_edge_en_us.mp3` | 1.51s | 0.85s | 1.0 | latin | This is a fashion business, so pizza is not available here. You can as |
| edge_en_in | `sample07_edge_en_in.mp3` | 2.06s | 5.21s | 0.917 | latin | This is a fashion business, so Pisa is not available here. You can ask |
| edge_ur_pk | `sample07_edge_ur_pk.mp3` | 1.35s | 0.8s | 1.0 | latin | This is a fashion business, so pizza is not available here. You can as |
| windows_sapi | `sample07_sapi.wav` | 0.08s | 5.7s | 1.0 | latin | This is a fashion business, so pizza is not available here. You can as |

### Sample 8 (english, tenant: captured)

**Asked:** (stored sample)

**Reply:** Draft ready: 2x Black Formal Shoes. Total: PKR 10000. Delivery or pickup?

| Engine | File | Synth | STT | Content recall | Script | Whisper heard |
|---|---|---|---|---|---|---|
| edge_en_us | `sample08_edge_en_us.mp3` | 1.31s | 0.84s | 1.0 | latin | Draft ready, 2X black formal shoes. Total, PKR 10,000. Delivery or pic |
| edge_en_in | `sample08_edge_en_in.mp3` | 1.75s | 5.0s | 1.0 | latin | Draft ready, 2X black formal shoes. Total, PKR 10,000. Delivery or pic |
| edge_ur_pk | `sample08_edge_ur_pk.mp3` | 1.3s | 0.83s | 0.818 | latin | Draft ready, 2X black formal shoes. Total, 10,000. Delivery or pick-up |
| windows_sapi | `sample08_sapi.wav` | 0.11s | 5.88s | 1.0 | latin | Draft ready, 2X black formal shoes. Total, PKR 10,000. Delivery or pic |

## Verdict (fill in after listening)

```text
Chosen route (a english-only / b transliterate / c multilingual): ______
Chosen voice:                                                     ______
Reason:                                                           ______
Acceptable on a phone call? (yes/no)                              ______
```

Record this in the FYP report as the justification for D1.