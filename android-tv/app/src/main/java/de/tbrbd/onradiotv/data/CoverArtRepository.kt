package de.tbrbd.onradiotv.data

import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

/**
 * Simplified port of app/cover_provider.py's iTunes Search lookup (the
 * primary, highest-hit-rate source there). The MusicBrainz/Cover Art
 * Archive and Amazon fallbacks from the Python side are intentionally left
 * out of this first version - see the project README.
 */
class CoverArtRepository(private val client: OkHttpClient) {

    private val cache = mutableMapOf<String, String?>()
    private val sizeRegex = Regex("/[^/]+\\.(jpg|jpeg|png|webp)$", RegexOption.IGNORE_CASE)

    fun findCoverUrl(artist: String, title: String): String? {
        val key = "${artist.lowercase()}|${title.lowercase()}"
        cache[key]?.let { return it }
        if (cache.containsKey(key)) return null // cached "no result"

        val query = "$artist $title".trim()
        if (query.isBlank()) return null

        val url = "https://itunes.apple.com/search".toHttpUrl().newBuilder()
            .addQueryParameter("term", query)
            .addQueryParameter("media", "music")
            .addQueryParameter("entity", "song")
            .addQueryParameter("limit", "5")
            .addQueryParameter("country", "DE")
            .build()

        val result = try {
            client.newCall(Request.Builder().url(url).build()).execute().use { response ->
                if (!response.isSuccessful) return@use null
                val body = response.body?.string() ?: return@use null
                val results = JSONObject(body).optJSONArray("results") ?: return@use null
                var best: String? = null
                for (i in 0 until results.length()) {
                    val item = results.getJSONObject(i)
                    val artwork = item.optString("artworkUrl100").ifBlank { item.optString("artworkUrl60") }
                    if (artwork.isNotBlank()) {
                        best = upsizeArtwork(artwork, size = 600)
                        break
                    }
                }
                best
            }
        } catch (_: Exception) {
            null
        }

        cache[key] = result
        return result
    }

    private fun upsizeArtwork(url: String, size: Int): String {
        return sizeRegex.replace(url) { match ->
            val ext = match.groupValues[1]
            val suffix = if (Regex("""\d+x\d+bb\.""", RegexOption.IGNORE_CASE).containsMatchIn(match.value)) "bb" else "-999"
            "/${size}x${size}${suffix}.$ext"
        }
    }
}
