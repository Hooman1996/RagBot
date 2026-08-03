document.addEventListener("DOMContentLoaded", async () => {

  Chat.init();
  await Sessions.load();  // ADD THIS
     CategoryFilter.init();
  try {
    const health = await API.health();
    const dot = document.getElementById("healthDot");
    if(health.status === "healthy")
      dot.classList.add("dot-green");
    else
      dot.classList.add("dot-red");
  } catch(e) {
    console.error(e);
  }

});
