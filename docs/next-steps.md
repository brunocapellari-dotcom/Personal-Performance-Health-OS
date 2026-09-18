# Next Steps — canonical execution order

The project continues as one final system. These steps are acceptance sequencing, not separate MVPs.

1. **Public runner unlock**
   - Change repository visibility from private to public.
   - The default-branch `public` workflow automatically deletes pre-public Actions runs and dispatches full CI + CodeQL.

2. **Complete current-tree regression**
   - Backend, PostgreSQL, Android and container must all pass on the same commit.
   - Fix defects; do not disable or reduce gates to obtain green status.

3. **Release evidence**
   - Run `release-artifacts` after the complete gate is green.
   - Preserve APK/container checksums, CycloneDX SBOM and GitHub/Sigstore attestations.

4. **Production infrastructure**
   - Managed PostgreSQL.
   - TLS endpoint.
   - Secret manager/KMS for bootstrap, JWT, audit, blob and backup keys.
   - Encrypted backup/restore drill.

5. **Android production path**
   - Real API base URL.
   - Release signing outside the repository.
   - Health Connect permissions and differential sync on a physical Android device.
   - Verify Room/SQLCipher persistence across restart, offline use and reconnection.

6. **Full operational data flow**
   - Goals/environment/readiness/events/nutrition sync.
   - `Monta meu próximo bloco`.
   - Independent audit.
   - Performed-session ingestion.
   - Recalculated next prescription.

7. **Shared-service integrations**
   - Calendar through scoped availability contract.
   - Research AI supplies evidence packages.
   - Segundo Cérebro supplies validated knowledge; no duplicate corpus.
   - Read-only MCP only after permissions model is proven.

8. **Final acceptance**
   - Real-device Android → Health Connect → encrypted local DB → authenticated sync → PostgreSQL → planner → auditor → performed session → changed next prescription.
   - Promote only when this passes together with automated regression.
