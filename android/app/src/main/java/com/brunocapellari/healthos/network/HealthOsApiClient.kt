package com.brunocapellari.healthos.network

import com.brunocapellari.healthos.security.DeviceIdentity
import okhttp3.MediaType.Companion.toMediaType
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

    fun enroll(bootstrapToken: String, identity: DeviceIdentity): JSONObject = post(
        path = "/v1/devices/enroll",
        body = JSONObject()
            .put("device_id", identity.deviceId())
            .put("public_key_pem", identity.publicKeyPem())
            .put("role", "owner_device"),
        bearer = bootstrapToken,
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

    private fun post(path: String, body: JSONObject, bearer: String? = null): JSONObject {
        val builder = Request.Builder()
            .url(root + path)
            .post(body.toString().toRequestBody(jsonMediaType))
        if (bearer != null) builder.header("Authorization", "Bearer $bearer")
        return execute(builder.build())
    }

    private fun get(path: String, bearer: String): JSONObject {
        val request = Request.Builder()
            .url(root + path)
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
