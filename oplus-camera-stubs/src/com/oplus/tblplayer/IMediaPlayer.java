package com.oplus.tblplayer;

import android.net.Uri;
import android.view.Surface;

public interface IMediaPlayer {
    interface OnPreparedListener {
        void onPrepared(IMediaPlayer mp);
    }

    interface OnCompletionListener {
        void onCompletion(IMediaPlayer mp);
    }

    interface OnErrorListener {
        boolean onError(IMediaPlayer mp, int what, int extra);
    }

    void setDataSource(Uri uri);

    void setSurface(Surface surface);

    void setVolume(float volume);

    void setOnPreparedListener(OnPreparedListener listener);

    void setOnCompletionListener(OnCompletionListener listener);

    void setOnErrorListener(OnErrorListener listener);

    void prepareAsync();

    void start();

    void pause();

    void stop();

    void reset();

    void release();
}
