package com.brunocapellari.healthos.network

import com.brunocapellari.healthos.security.DeviceIdentity
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException

class HealthOsApiClient(
    baseUrl: String,
    private val http: OkHttpClient = OkHttpClient(),
) {
    private val root = baseUrl.trimEnd('/')
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    fun enroll(linkToken: String, identity: DeviceIdentity, role: String = "owner_device"): JSONObject = post(
        path = "/v1/devices/enroll",
        body = JSONObject()
            .put("device_id", identity.deviceId())
            .put("public_key_pem", identity.publicKeyPem())
            .put("role", role),
        bearer = linkToken,
    )

    fun createPairingToken(
        token: String,
        role: String = "owner_device",
        ttlSeconds: Int = 300,
    ): JSONObject = post(
        path = "/v1/devices/pairing-token",
        body = JSONObject()
            .put("role", role)
            .put("ttl_seconds", ttlSeconds),
        bearer = token,
    )

    fun authenticate(identity: DeviceIdentity): String {
        val challenge = post(
            path = "/v1/auth/challenge",
            body = JSONObject().put("device_id", identity.deviceId()),
        )
        val verified = post(
            path = "/v1/auth/verify",
            body = JSONObject()
                .put("challenge_id", challenge.getString("challenge_id"))
                .put("signature_b64", identity.signBase64(challenge.getString("nonce"))),
        )
        return verified.getString("access_token")
    }

    fun push(token: String, changes: JSONArray): JSONObject = post(
        path = "/v1/sync/push",
        body = JSONObject().put("changes", changes),
        bearer = token,
    )

    fun pull(token: String, after: Long): JSONObject = get(
        path = "/v1/sync/pull?after=$after&limit=500",
        bearer = token,
    )

    fun nextBlock(token: String, request: JSONObject): JSONObject = post(
        path = "/v1/plans/next-block",
        body = request,
        bearer = token,
    )

    fun dashboard(token: String, today: String): JSONObject = get(
        path = "/v1/dashboard?today=$today",
        bearer = token,
    )

    fun trainingHistory(token: String, days: Int, today: String): JSONObject {
        require(days in 7..3660) { "history days must be between 7 and 3660" }
        val url = (root + "/v1/training/history").toHttpUrl().newBuilder()
            .addQueryParameter("days", days.toString())
            .addQueryParameter("today", today)
            .build()
        return get(url, token)
    }

    fun nutritionHistory(token: String, start: String, end: String): JSONObject {
        val url = (root + "/v1/nutrition/history").toHttpUrl().newBuilder()
            .addQueryParameter("start", start)
            .addQueryParameter("end", end)
            .build()
        return get(url, token)
    }

    fun lookupFoodBarcode(token: String, barcode: String): JSONObject {
        require(barcode.matches(Regex("^\\d{4,24}$"))) { "barcode must contain 4 to 24 digits" }
        return get(path = "/v1/nutrition/barcode/$barcode", bearer = token)
    }

    fun searchFoods(token: String, query: String): JSONObject {
        val normalized = query.trim().replace(Regex("\\s+"), " ")
        require(normalized.length in 1..200) { "nutrition query must contain 1 to 200 characters" }
        val url = (root + "/v1/nutrition/search").toHttpUrl().newBuilder()
            .addQueryParameter("q", normalized)
            .build()
        return execute(
            Request.Builder()
                .url(url)
                .header("Authorization", "Bearer $token")
                .get()
                .build(),
        )
    }

    private fun post(path: String, body: JSONObject, bearer: String? = null): JSONObject {
        val builder = Request.Builder()
            .url(root + path)
            .post(body.toString().toRequestBody(jsonMediaType))
        if (bearer != null) builder.header("Authorization", "Bearer $bearer")
        return execute(builder.build())
    }

    private fun get(path: String, bearer: String): JSONObject = get((root + path).toHttpUrl(), bearer)

    private fun get(url: okhttp3.HttpUrl, bearer: String): JSONObject {
        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $bearer")
            .get()
            .build()
        return execute(request)
    }

    private fun execute(request: Request): JSONObject = http.newCall(request).execute().use { response ->
        val raw = response.body.string()
        if (!response.isSuccessful) {
            throw IOException("Health OS API ${response.code}: ${raw.take(512)}")
        }
        if (raw.isBlank()) JSONObject() else JSONObject(raw)
    }
}
