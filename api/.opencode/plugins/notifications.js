// Notification plugin for OpenCode
// Sends macOS notifications when sessions complete or errors occur

export const NotificationPlugin = async ({ project, client, $, directory, worktree }) => {
  console.log("Notification plugin initialized")
  
  return {
    // Notify when a session completes
    "session.idle": async (input, output) => {
      try {
        await $`osascript -e 'display notification "Session completed successfully" with title "OpenCode"'`
      } catch (error) {
        console.log("Failed to send notification:", error)
      }
    },
    
    // Notify on errors
    "session.error": async (input, output) => {
      try {
        const errorMessage = output.error?.message || "Unknown error"
        await $`osascript -e 'display notification "Error: ${errorMessage}" with title "OpenCode" subtitle "Session failed"'`
      } catch (error) {
        console.log("Failed to send error notification:", error)
      }
    },
    
    // Log session starts
    "session.created": async (input, output) => {
      await client.app.log({
        body: {
          service: "notifications",
          level: "info",
          message: "New session created",
          directory,
          worktree
        }
      })
    }
  }
}