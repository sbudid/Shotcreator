/* mp4defrag.js — ubah fragmented MP4 (keluaran MediaRecorder Chrome)
 * menjadi MP4 biasa dengan metadata durasi yang benar.
 *
 * Masalah: MediaRecorder Chrome menulis video/mp4 sebagai fragmented MP4
 * (deretan moof+mdat) dengan mvhd duration=0 dan tanpa sample table.
 * Browser bisa memutarnya, tapi banyak aplikasi (galeri HP, dsb.)
 * membaca durasinya salah (mis. 00:06 untuk video 33 detik).
 *
 * defragMp4(arrayBuffer) -> Uint8Array MP4 biasa (ftyp, mdat, moov).
 * Kalau input bukan fragmented MP4 (tidak ada moof), input dikembalikan
 * apa adanya.
 */
"use strict";

function dfReadU32(dv, off) { return dv.getUint32(off, false); }
function dfReadU64(dv, off) {
  return Number(dv.getBigUint64(off, false));
}

function dfBox(dv, off) {
  const size = dfReadU32(dv, off);
  const type = String.fromCharCode(
    dv.getUint8(off + 4), dv.getUint8(off + 5),
    dv.getUint8(off + 6), dv.getUint8(off + 7));
  let hlen = 8, sz = size;
  if (sz === 1) { sz = dfReadU64(dv, off + 8); hlen = 16; }
  return { type, size: sz, hlen };
}

function dfChildren(dv, off, size, hlen) {
  const out = [];
  let p = off + hlen;
  const end = off + size;
  while (p + 8 <= end) {
    const b = dfBox(dv, p);
    if (b.size < 8 || p + b.size > end) break;
    out.push({ ...b, off: p });
    p += b.size;
  }
  return out;
}

function dfFind(dv, off, size, hlen, type) {
  return dfChildren(dv, off, size, hlen).filter((b) => b.type === type);
}

/* Kumpulkan semua track dari moov: id, timescale, hdlr, dan box mentah
 * yang perlu disalin (tkhd, hdlr, vmhd/smhd, dinf, stsd).
 * Offset versi-1 (dari byte mentah file Chrome):
 *   tkhd v1: track_ID @ +28, duration @ +36 (u64)
 *   mdhd v1: timescale @ +28, duration @ +32 (u64) */
function dfParseTracks(dv, moov) {
  const tracks = [];
  for (const trak of dfFind(dv, moov.off, moov.size, moov.hlen, "trak")) {
    const tkhd = dfFind(dv, trak.off, trak.size, trak.hlen, "tkhd")[0];
    const mdia = dfFind(dv, trak.off, trak.size, trak.hlen, "mdia")[0];
    const mdhd = dfFind(dv, mdia.off, mdia.size, mdia.hlen, "mdhd")[0];
    const hdlr = dfFind(dv, mdia.off, mdia.size, mdia.hlen, "hdlr")[0];
    const minf = dfFind(dv, mdia.off, mdia.size, mdia.hlen, "minf")[0];
    const stbl = dfFind(dv, minf.off, minf.size, minf.hlen, "stbl")[0];
    const stsd = dfFind(dv, stbl.off, stbl.size, stbl.hlen, "stsd")[0];
    const ver = dv.getUint8(tkhd.off + tkhd.hlen);
    const trackId = dfReadU32(dv, tkhd.off + (ver === 1 ? 28 : 20));
    const mver = dv.getUint8(mdhd.off + mdhd.hlen);
    const timescale = dfReadU32(dv, mdhd.off + (mver === 1 ? 28 : 20));
    const handler = String.fromCharCode(
      dv.getUint8(hdlr.off + hdlr.hlen + 8), dv.getUint8(hdlr.off + hdlr.hlen + 9),
      dv.getUint8(hdlr.off + hdlr.hlen + 10), dv.getUint8(hdlr.off + hdlr.hlen + 11));
    const mediaHdr = ["vmhd", "smhd", "hmhd", "sthd"].map((t) =>
      dfFind(dv, minf.off, minf.size, minf.hlen, t)[0]).find(Boolean);
    const dinf = dfFind(dv, minf.off, minf.size, minf.hlen, "dinf")[0];
    tracks.push({
      id: trackId, timescale, handler, tkhd, mdhd, hdlr, minf, stbl, stsd,
      mediaHdr, dinf, samples: [],
    });
  }
  return tracks;
}

/* Ambil sample dari semua moof. Kembalikan false kalau tidak ada moof. */
function dfCollectSamples(dv, fileLen, tracksById) {
  let p = 0, foundMoof = false;
  while (p + 8 <= fileLen) {
    const b = dfBox(dv, p);
    if (b.size < 8 || p + b.size > fileLen) break;
    if (b.type === "moof") {
      foundMoof = true;
      for (const traf of dfFind(dv, p, b.size, b.hlen, "traf")) {
        const tfhd = dfFind(dv, traf.off, traf.size, traf.hlen, "tfhd")[0];
        const truns = dfFind(dv, traf.off, traf.size, traf.hlen, "trun");
        const tflags = dfReadU32(dv, tfhd.off + tfhd.hlen) & 0xffffff;
        const trackId = dfReadU32(dv, tfhd.off + tfhd.hlen + 4);
        const track = tracksById.get(trackId);
        if (!track) continue;
        let defDur = 0, defSize = 0;
        let q = tfhd.off + tfhd.hlen + 8;
        if (tflags & 0x1) q += 8;                    // base-data-offset
        if (tflags & 0x2) q += 4;                    // sample-description-index
        if (tflags & 0x8) { defDur = dfReadU32(dv, q); q += 4; }
        if (tflags & 0x10) { defSize = dfReadU32(dv, q); q += 4; }
        if (tflags & 0x20) q += 4;                  // default-sample-flags
        const baseIsMoof = (tflags & 0x20000) !== 0;
        for (const trun of truns) {
          const flags = dfReadU32(dv, trun.off + trun.hlen) & 0xffffff;
          const n = dfReadU32(dv, trun.off + trun.hlen + 4);
          let r = trun.off + trun.hlen + 8;
          let dataOff = 0;
          if (flags & 0x1) { dataOff = dv.getInt32(r, false); r += 4; }
          if (flags & 0x4) r += 4;                   // first-sample-flags
          const base = baseIsMoof || !(tflags & 0x1) ? p : 0;
          let samplePos = base + dataOff;
          for (let i = 0; i < n; i++) {
            let dur = defDur, size = defSize;
            if (flags & 0x100) { dur = dfReadU32(dv, r); r += 4; }
            if (flags & 0x200) { size = dfReadU32(dv, r); r += 4; }
            if (flags & 0x400) r += 4;
            if (flags & 0x800) r += 4;
            track.samples.push({ dur, size, off: samplePos });
            samplePos += size;
          }
        }
      }
    }
    p += b.size;
  }
  return foundMoof;
}

/* NAL unit pertama bertipe 5 (IDR) => keyframe. Sample AVCC: [len32][nal]... */
function dfIsKeyframe(u8, off, size) {
  let p = off;
  const end = off + size;
  while (p + 4 <= end) {
    const nlen = (u8[p] << 24) | (u8[p + 1] << 16) | (u8[p + 2] << 8) | u8[p + 3];
    if (nlen <= 0 || p + 4 + nlen > end) break;
    const nalType = u8[p + 4] & 0x1f;
    if (nalType === 5) return true;
    if (nalType === 1) return false;
    p += 4 + nlen;
  }
  return false;
}

/* ---- penulis box ---- */
function dfWriter() {
  const parts = [];
  let len = 0;
  return {
    u32(v) { const b = new Uint8Array(4); new DataView(b.buffer).setUint32(0, v, false); parts.push(b); len += 4; },
    u16(v) { const b = new Uint8Array(2); new DataView(b.buffer).setUint16(0, v, false); parts.push(b); len += 2; },
    u8(v) { parts.push(new Uint8Array([v])); len += 1; },
    bytes(b) { parts.push(b); len += b.length; },
    box(type, fn) {
      const w = dfWriter();
      fn(w);
      const body = w.concat();
      this.u32(8 + body.length);
      for (const ch of type) this.u8(ch.charCodeAt(0));
      this.bytes(body);
    },
    concat() {
      const out = new Uint8Array(len);
      let o = 0;
      for (const b of parts) { out.set(b, o); o += b.length; }
      return out;
    },
    length() { return len; },
  };
}

function dfCopyBox(w, u8, box) {
  w.bytes(u8.subarray(box.off, box.off + box.size));
}

/**
 * Defragmentasi MP4: ArrayBuffer -> Uint8Array MP4 biasa.
 * Mengembalikan input apa adanya jika bukan fragmented MP4.
 */
function defragMp4(arrayBuffer) {
  const u8 = new Uint8Array(arrayBuffer);
  const dv = new DataView(arrayBuffer);
  const fileLen = u8.length;

  // kumpulkan ftyp + moov
  let ftyp = null, moov = null;
  let p = 0;
  while (p + 8 <= fileLen) {
    const b = dfBox(dv, p);
    if (b.size < 8 || p + b.size > fileLen) break;
    if (b.type === "ftyp") ftyp = { ...b, off: p };
    if (b.type === "moov") moov = { ...b, off: p };
    p += b.size;
  }
  if (!moov) return u8;

  const tracks = dfParseTracks(dv, moov);
  if (!tracks.length) return u8;
  const byId = new Map(tracks.map((t) => [t.id, t]));
  if (!dfCollectSamples(dv, fileLen, byId)) return u8; // bukan fragmented
  if (!tracks.every((t) => t.samples.length)) return u8;

  // tandai keyframe (video saja; audio selalu sync)
  for (const t of tracks) {
    if (t.handler === "vide") {
      t.sync = [];
      t.samples.forEach((s, i) => {
        if (dfIsKeyframe(u8, s.off, s.size)) t.sync.push(i + 1);
      });
      if (!t.sync.length) t.sync = null; // anggap semua sync
    } else {
      t.sync = null;
    }
    t.totalDur = t.samples.reduce((a, s) => a + s.dur, 0);
  }

  const MVHD_TS = 1000;
  const movieDur = Math.max(...tracks.map((t) =>
    Math.round((t.totalDur / t.timescale) * MVHD_TS)));

  const mdatDataLen = tracks.reduce((a, t) =>
    a + t.samples.reduce((x, s) => x + s.size, 0), 0);

  // tulis ftyp + mdat dulu (offset chunk diketahui), lalu moov
  const w = dfWriter();
  if (ftyp) dfCopyBox(w, u8, ftyp);
  w.u32(8 + mdatDataLen);
  w.u8(109); w.u8(100); w.u8(97); w.u8(116); // "mdat"
  const chunkOff = {};
  for (const t of tracks) {
    chunkOff[t.id] = w.length();
    const buf = new Uint8Array(t.samples.reduce((a, s) => a + s.size, 0));
    let o = 0;
    for (const s of t.samples) {
      buf.set(u8.subarray(s.off, s.off + s.size), o);
      o += s.size;
    }
    w.bytes(buf);
  }

  // ---- moov ----
  w.box("moov", (mw) => {
    mw.box("mvhd", (b) => {
      b.u32(0); b.u32(0); b.u32(0);       // version+flags, creation, modification
      b.u32(MVHD_TS); b.u32(movieDur);    // timescale, duration
      b.u32(0x00010000); b.u16(0x0100); b.u16(0); // rate, volume
      b.u16(0); b.u16(0); b.u32(0); b.u32(0);     // reserved
      // matrix identity
      b.u32(0x00010000); b.u32(0); b.u32(0);
      b.u32(0); b.u32(0x00010000); b.u32(0);
      b.u32(0); b.u32(0); b.u32(0x40000000);
      for (let i = 0; i < 6; i++) b.u32(0);       // pre-defined
      b.u32(tracks.length + 1);                   // next-track-ID
    });
    for (const t of tracks) {
      mw.box("trak", (tk) => {
        // tkhd: salin lalu patch durasi (v1: u64 @ +36, v0: u32 @ +28)
        const tkhdRaw = u8.slice(t.tkhd.off, t.tkhd.off + t.tkhd.size).slice();
        const tkv = tkhdRaw[8];
        const tkDur = Math.round((t.totalDur / t.timescale) * MVHD_TS);
        const tkDv = new DataView(tkhdRaw.buffer);
        if (tkv === 1) tkDv.setBigUint64(36, BigInt(tkDur), false);
        else tkDv.setUint32(28, tkDur, false);
        tk.bytes(tkhdRaw);
        tk.box("mdia", (md) => {
          md.box("mdhd", (b) => {
            b.u32(0); b.u32(0); b.u32(0);
            b.u32(t.timescale); b.u32(t.totalDur);
            b.u16(0x55c4); b.u16(0); // language=und, quality
          });
          dfCopyBox(md, u8, t.hdlr);
          md.box("minf", (mf) => {
            if (t.mediaHdr) dfCopyBox(mf, u8, t.mediaHdr);
            dfCopyBox(mf, u8, t.dinf);
            mf.box("stbl", (st) => {
              dfCopyBox(st, u8, t.stsd);
              // stts
              st.box("stts", (b) => {
                b.u32(0);
                const runs = [];
                for (const s of t.samples) {
                  const last = runs[runs.length - 1];
                  if (last && last[1] === s.dur) last[0]++;
                  else runs.push([1, s.dur]);
                }
                b.u32(runs.length);
                for (const [c, d] of runs) { b.u32(c); b.u32(d); }
              });
              // stsc: satu chunk
              st.box("stsc", (b) => {
                b.u32(0); b.u32(1);
                b.u32(1); b.u32(t.samples.length); b.u32(1);
              });
              // stsz
              st.box("stsz", (b) => {
                b.u32(0); b.u32(0); b.u32(t.samples.length);
                for (const s of t.samples) b.u32(s.size);
              });
              // stco
              st.box("stco", (b) => {
                b.u32(0); b.u32(1); b.u32(chunkOff[t.id]);
              });
              // stss (kalau tidak semua sync)
              if (t.sync && t.sync.length !== t.samples.length) {
                st.box("stss", (b) => {
                  b.u32(0); b.u32(t.sync.length);
                  for (const n of t.sync) b.u32(n);
                });
              }
            });
          });
        });
      });
    }
  });

  return w.concat();
}

if (typeof module !== "undefined") module.exports = { defragMp4 };
