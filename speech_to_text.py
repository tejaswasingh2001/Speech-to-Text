# -*- coding: utf-8 -*-
"""Copy of Voice_to_text.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1ftjH54xOrXMRHLj3MeiZ-DboDzDsigXv
"""

!pip install jiwer

!pip install tensorflow

import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import matplotlib.pyplot as plt
from IPython import display
from jiwer import wer

data_url = "https://data.keithito.com/data/speech/LJSpeech-1.1.tar.bz2"
data_path = keras.utils.get_file("LJSpeech-1.1", data_url, untar=True)

!nvidia-smi

wavs_path = data_path + "/wavs/"
metadata_path = data_path + "/metadata.csv"

#read metadata file and parsing it
metadata_df = pd.read_csv(metadata_path, sep="|", header=None, quoting=3)

metadata_df.head(10)

metadata_df.columns = ["file_name","transcription", "normalized_transcription"]
metadata_df = metadata_df[["file_name", "normalized_transcription"]]
metadata_df = metadata_df.sample(frac=1).reset_index(drop=True)
metadata_df.head(5)

#splittinf data for traning and validation of our model
split = int(len(metadata_df) * 0.85)
df_train = metadata_df[:split]
df_val = metadata_df[split:]

print(f"Size of the training set: {len(df_train)}")
print(f"Size of the validation set: {len(df_val)}")

#set of characters accepted 
characters = [x for x in "abcdefghijklmnopqrstuvwxyz'?! "]
#mapping char to int
char_to_num = keras.layers.StringLookup(
    vocabulary=characters, oov_token=""
)
#mapping int back to original chars
num_to_char = keras.layers.StringLookup(
    vocabulary=char_to_num.get_vocabulary(), oov_token=", invert=True"
)

print(
    f"the vocabulary is: {char_to_num.get_vocabulary()}"
    f"(size={char_to_num.vocabulary_size()})"
)

frame_length = 256

frame_step = 160

fft_length = 384

def encode_single_sample(wav_file, label):
    #processing the audio
    
        #reading
        file = tf.io.read_file(wavs_path + wav_file + ".wav")
        #decoding
        audio, _ = tf.audio.decode_wav(file)
        audio = tf.squeeze(audio, axis=-1)
        #changing type to float
        audio = tf.cast(audio, tf.float32)
        
        #getting spectrogram
        spectrogram = tf.signal.stft(
            audio, frame_length=frame_length, frame_step=frame_step, fft_length=fft_length
        )
        #magnitiude is needed only
        spectrogram = tf.abs(spectrogram)
        spectrogram = tf.math.pow(spectrogram,0.5)

        #normalisation
        means = tf.math.reduce_mean(spectrogram, 1, keepdims=True)
        stddevs = tf.math.reduce_std(spectrogram, 1, keepdims=True)
        spectrogram = (spectrogram-means)/(stddevs+1e-10)
        
        #processing and converting label to lowercase
        label = tf.strings.lower(label)
        #splitting label
        label = tf.strings.unicode_split(label, input_encoding="UTF-8")
        #mapping char(in label)-> numbers
        label = char_to_num(label)
        
        return spectrogram, label

batch_size = 32

train_dataset = tf.data.Dataset.from_tensor_slices(
        (list(df_train["file_name"]), list(df_train["normalized_transcription"]))
)

train_dataset = (
    train_dataset.map(encode_single_sample, num_parallel_calls=tf.data.AUTOTUNE)
    .padded_batch(batch_size)
    .prefetch(buffer_size=tf.data.AUTOTUNE)
)

validation_dataset = tf.data.Dataset.from_tensor_slices(
        (list(df_val["file_name"]), list(df_val["normalized_transcription"]))
)

validation_dataset = (
    validation_dataset.map(encode_single_sample, num_parallel_calls=tf.data.AUTOTUNE)
    .padded_batch(batch_size)
    .prefetch(buffer_size=tf.data.AUTOTUNE)
)

fig = plt.figure(figsize=(8,5)) 
for batch in train_dataset.take(1):
    spectrogram = batch[0][0].numpy()
    spectrogram = np.array([np.trim_zeros(x) for x in np.transpose(spectrogram)])
    label = batch[1][0]
    
    #spectrogram
    label = tf.strings.reduce_join(num_to_char(label)).numpy().decode("utf-8")
    ax = plt.subplot(2,1,1)
    ax.imshow(spectrogram, vmax=1)
    ax.set_title(label)
    ax.axis("off")
    
    #wav
    file = tf.io.read_file(
        wavs_path + list(df_train["file_name"])[0] + ".wav"
    )
    audio, _ = tf.audio.decode_wav(file)
    audio = audio.numpy()
    ax = plt.subplot(2,1,2)
    plt.plot(audio)
    ax.set_title("Signal Wave")
    ax.set_xlim(0, len(audio))
    display.display(display,Audio(np.transpose(audio), rate = 16000))
plt.show()

def CTCLoss(y_true, y_pred):
    
    batch_len = tf.cast(tf.shape(y_true)[0], dtype="int64")
    input_len = tf.cast(tf.shape(y_pred)[1], dtype="int64")
    label_len = tf.cast(tf.shape(y_true)[1], dtype="int64")

    input_len = input_len * tf.ones(shape=(batch_len, 1), dtype="int64")
    label_len = input_len * tf.ones(shape=(batch_len, 1), dtype="int64")
    
    loss = keras.backend.ctc_batch_cost(y_true, y_pred, input_len, label_len)
    return loss

def dl_model(input_dim, output_dim, rnn_layers=5, rnn_units=128):
        
        input_spectrogram = layers.Input((None, input_dim), name="input")
        
        x = layers.Reshape((-1, input_dim, 1), name="expand_dim")(input_spectrogram)
        
        x = layers.Conv2D(
            filters = 32,
            kernel_size = [11, 41],
            strides = [2,2],
            padding = "same",
            use_bias = False,
            name = "conv_1"
        )(x)
        
        x = layers.BatchNormalization(name="conv_1_bn")(x)
        x = layers.ReLU(name="conv_1_relu")(x)
        
        x = layers.Conv2D(
            filters = 32,
            kernel_size = [11, 41],
            strides = [2,2],
            padding = "same",
            use_bias = False,
            name = "conv_2"
        )(x) 
        
        x = layers.BatchNormalization(name="conv_2_bn")(x)
        x = layers.ReLU(name="conv_2_relu")(x)
        
        x = layers.Reshape((-1, x.shape[-2] * x.shape[-1]))(x)
        
        for i in range(1, rnn_layers+1):
            recurrent = layers.GRU(
                units = rnn_units,
                activation = "tanh",
                recurrent_activation = "sigmoid",
                use_bias = True,
                return_sequences = True,
                reset_after = True,
                name = f"gru_{i}",
            )
            x = layers.Bidirectional(
                recurrent, name=f"bidirectional_{i}", merge_mode="concat"
            )(x)
            if i < rnn_layers:
                x = layers.Dropout(rate=0.5)(x)
        
        x = layers.Dense(units=rnn_units*2, name="dense_1")(x)
        x = layers.ReLU(name="dense_1_relu")(x)
        x = layers.Dropout(rate=0.5)(x)
        
        output = layers.Dense(units=output_dim+1, activation="softmax")(x)
        
        model = keras.Model(input_spectrogram, output, name="VoiceToTEXT")
        
        opt = keras.optimizers.Adam(learning_rate=1e-4)
        
        model.compile(optimizer=opt, loss=CTCLoss)
        return model    
    
    
model = dl_model(
    input_dim = fft_length // 2 + 1,
    output_dim = char_to_num.vocabulary_size(),
    rnn_units=512
)

model.summary(line_length=110)

#Training

#funct to decode output of the netwrk
def dcode_batch_prediction(pred):
    input_len = np.ones(pred.shape[0])*pred.shape[1]
    #using greedy srch    
    results = keras.backend.ctc_decode(pred, input_length=input_len, greedy=True)[0][0]
    # iterating ovr rslt and getting back to txt
    output_text = []
    for result in results:
        result = tf.strings.reduce_join(num_to_char(result)).numpy().decode("utf-8")
        output_text.append(result)
    
    return output_text

epochs = 2


history = model.fit(
    train_dataset,
    validation_data = validation_dataset,
    epochs = epochs,
)

predictions = []
targets = []
for batch in validation_dataset:
    X, y = batch
    batch_predictions = model.predict(X)
    batch_predictions = dcode_batch_prediction(batch_predictions)
    predictions.extend(batch_predictions)
    for label in y:
        label = tf.strings.reduce_join(num_to_char(label)).numpy().decode("utf-8")
        targets.append(label)
    wer_score = wer(targets, predictions)
    print("." * 100)
    print(f"Word Error Rate: {wer_score:.4f}")
    print("." * 100)
    for i in np.random.rabdint(0, len(predictions), 5):
        print(f"Target      : {targets[i]}")
        print(f"Prediction  : {predictions[i]}")
        print("." * 100)